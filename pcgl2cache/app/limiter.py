"""Per-user rate limiting.

Modelled on MaterializationEngine's materializationengine/limiter.py, with two
deliberate differences noted below.

WHY PER USER AND NOT PER IP
flask_limiter's default key is the remote address, which is useless here: every
request arrives from the ingress controller, and even the real client address is
shared -- the bulk sweep that prompted this came from
orcd-inband-gateway002.mit.edu, a NAT gateway in front of an entire research
computing cluster. Limiting by address would either do nothing (all requests look
like one ingress IP) or punish every user behind a shared gateway for one user's
job. middle_auth_client puts the authenticated identity on flask.g, so the bucket
is that identity.

WHY REDIS STORAGE MATTERS
The default "memory://" storage is per process. The api runs up to 30 replicas,
each with up to 16 uwsgi workers, so an in-memory limit of N/minute is really
N * 480/minute across the fleet -- effectively no limit at all. LIMITER_URI must
point at a shared Redis for the configured number to mean anything. This module
logs loudly at startup when it does not, because the failure is silent
otherwise: everything works, nothing is limited.
"""

import json
import logging
import os

from flask import g, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

logger = logging.getLogger(__name__)


def _load_categories(env_var):
    try:
        categories = json.loads(os.environ.get(env_var, "{}"))
    except json.JSONDecodeError:
        logger.warning("%s is not valid JSON; ignoring it", env_var)
        return {}
    return categories if isinstance(categories, dict) else {}


def get_rate_limit_from_config(category=None):
    if not category:
        return None
    return _load_categories("LIMITER_CATEGORIES").get(category)


def get_service_account_rate_limit(category, endpoint=None):
    """Elevated limit for service accounts, or None to apply the normal limit.

    Same two-tier scheme as MaterializationEngine: LIMITER_SERVICE_ACCOUNT_CATEGORIES
    raises a whole category, LIMITER_SERVICE_ACCOUNT_OVERRIDES raises one endpoint
    and wins where both apply. Both default to empty, so with no configuration a
    service account gets exactly the limit everyone else does.

    This exists because internal callers funnel through a single endpoint and would
    otherwise exhaust one bucket no matter how many replicas they run.
    """
    if endpoint:
        overrides = _load_categories("LIMITER_SERVICE_ACCOUNT_OVERRIDES").get(endpoint) or {}
        if isinstance(overrides, dict) and category in overrides:
            return overrides[category]
    return _load_categories("LIMITER_SERVICE_ACCOUNT_CATEGORIES").get(category)


def is_service_account():
    """True when the caller authenticated with a service account token.

    middle_auth_client populates flask.g.auth_user from the auth service's
    /user/cache response, which carries `service_account`. Auth decorators run
    before the limiter, so this is readable by the time a limit is evaluated.
    """
    user = getattr(g, "auth_user", None)
    if not isinstance(user, dict):
        return False
    return bool(user.get("service_account"))


def user_key():
    """Bucket key: the authenticated user id, falling back to the client address.

    The fallback matters for the endpoints that carry no auth decorator
    (/attribute_metadata, /table_mapping). Without it flask_limiter raises a
    KeyError inside the request and turns a rate-limit miss into a 500.

    Prefixed so a user id can never collide with an address.
    """
    user = getattr(g, "auth_user", None)
    if isinstance(user, dict) and user.get("id") is not None:
        return f"user:{user['id']}"
    return f"addr:{get_remote_address() or 'unknown'}"


def limit_by_category(category, endpoint=None):
    """Rate limit an endpoint per authenticated user.

    Returns a no-op decorator when nothing is configured, so importing and
    applying this is safe on a deployment that has set no limits at all.
    """
    limit = get_rate_limit_from_config(category)
    service_account_limit = get_service_account_rate_limit(category, endpoint)

    if limit is None and service_account_limit is None:
        return lambda f: f

    if service_account_limit is None:
        return limiter.limit(limit, key_func=user_key)

    def decorator(func):
        # Two limits, each exempt when the other applies, so exactly one is ever
        # enforced. Service accounts still get a real ceiling -- exempting them
        # entirely would just move the pressure onto Bigtable.
        func = limiter.limit(
            service_account_limit,
            key_func=user_key,
            exempt_when=lambda: not is_service_account(),
        )(func)
        if limit is not None:
            func = limiter.limit(
                limit,
                key_func=user_key,
                exempt_when=is_service_account,
            )(func)
        return func

    return decorator


def init_app(app):
    """Attach the limiter and warn about configurations that silently do nothing."""
    limiter.init_app(app)

    storage = os.environ.get("LIMITER_URI", "memory://")
    categories = _load_categories("LIMITER_CATEGORIES")
    if not categories:
        app.logger.info("rate limiting: no LIMITER_CATEGORIES set, limits are not enforced")
    elif storage.startswith("memory://"):
        # Worth shouting about: the limits look configured and are per process, so
        # the real fleet-wide ceiling is this number times replicas times workers.
        app.logger.warning(
            "rate limiting: LIMITER_CATEGORIES is set (%s) but LIMITER_URI is %r, "
            "which is per-process storage. Each uwsgi worker keeps its own counter, "
            "so the effective limit is multiplied by replicas x workers. Point "
            "LIMITER_URI at a shared Redis to enforce the configured value.",
            ",".join(sorted(categories)),
            storage,
        )
    else:
        app.logger.info(
            "rate limiting: enforcing %s via %s",
            ",".join(sorted(categories)),
            storage.split("@")[-1],  # never log credentials
        )


limiter = Limiter(
    # Default key; every limit this module registers overrides it with user_key.
    get_remote_address,
    storage_uri=os.environ.get("LIMITER_URI", "memory://"),
    default_limits=None,
    headers_enabled=True,  # X-RateLimit-* so callers can self-throttle
)
