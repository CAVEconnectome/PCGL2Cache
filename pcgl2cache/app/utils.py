import os
from functools import lru_cache
from typing import Iterable

import numpy as np
from flask import current_app
from flask import json
from cloudvolume import CloudVolume
from google.auth.credentials import Credentials
from kvdbclient import BigTableClient
from kvdbclient import get_default_client_info

from ..core import attributes


class DoNothingCreds(Credentials):
    def refresh(self, request):
        pass


def get_app_base_path():
    return os.path.dirname(os.path.realpath(__file__))


def get_instance_folder_path():
    return os.path.join(get_app_base_path(), "instance")


def jsonify_with_kwargs(data, as_response=True, **kwargs):
    kwargs.setdefault("separators", (",", ":"))
    # JSONIFY_PRETTYPRINT_REGULAR and JSONIFY_MIMETYPE were removed in Flask 2.3
    if current_app.json.compact == False or current_app.debug:
        kwargs["indent"] = 2
        kwargs["separators"] = (", ", ": ")

    resp = json.dumps(data, **kwargs)
    if as_response:
        return current_app.response_class(
            resp + "\n", mimetype=current_app.json.mimetype
        )
    else:
        return resp


@lru_cache(maxsize=32)
def _l2cache_client(l2cache_id: str) -> BigTableClient:
    """One BigTableClient per table, reused for the life of the worker.

    Constructing this per request builds a fresh gRPC channel each time. The channels
    are dropped immediately but the allocation churn sets the worker's heap high-water,
    which glibc never returns: a worker reaches ~68 MB above its post-import baseline
    within roughly 20 requests and then stays there. Long-lived clients are also what
    gRPC is designed for -- it reconnects internally, so there is nothing to refresh.

    Keyed on l2cache_id rather than graph_id so the cache stays correct if two graphs
    resolve to the same table, or if config is rebuilt.
    """
    info = get_default_client_info()
    return BigTableClient(l2cache_id, config=info.CONFIG)


@lru_cache(maxsize=32)
def _l2cache_cv(cv_path: str) -> CloudVolume:
    """One CloudVolume per path, reused for the life of the worker.

    Only metadata is read from it here (resolution, bounds, graph_chunk_size, meta),
    never voxel data, so sharing one instance across requests is safe. Constructing it
    per request re-parses the info document on every call.
    """
    return CloudVolume(cv_path)


def get_l2cache_client(graph_id: str) -> BigTableClient:
    l2cache_config = current_app.config["L2CACHE_CONFIG"]
    assert graph_id in l2cache_config, f"Dataset {graph_id} does not have an L2 Cache."

    return _l2cache_client(l2cache_config[graph_id]["l2cache_id"])


def get_l2cache_cv(graph_id: str) -> CloudVolume:
    l2cache_config = current_app.config["L2CACHE_CONFIG"]
    assert (
        graph_id in l2cache_config
    ), f"Dataset {graph_id} does not have CV graphene path."

    return _l2cache_cv(l2cache_config[graph_id]["cv_path"])


def toboolean(value):
    """Transform value to boolean type.
    :param value: bool/int/str
    :return: bool
    :raises: ValueError, if value is not boolean.
    """
    if not value:
        raise ValueError("Can't convert null to boolean")

    if isinstance(value, bool):
        return value
    try:
        value = value.lower()
    except:
        raise ValueError(f"Can't convert {value} to boolean")

    if value in ("true", "1"):
        return True
    if value in ("false", "0"):
        return False

    raise ValueError(f"Can't convert {value} to boolean")


def tobinary(ids):
    """Transform id(s) to binary format

    :param ids: uint64 or list of uint64s
    :return: binary
    """
    return np.array(ids).tobytes()


def tobinary_multiples(arr):
    """Transform id(s) to binary format

    :param arr: list of uint64 or list of uint64s
    :return: binary
    """
    return [np.array(arr_i).tobytes() for arr_i in arr]


def get_registered_attributes() -> dict:
    attrs = {
        attr.key.decode(): attr for attr in attributes.Attribute._attributes.values()
    }
    attrs.pop("meta")
    return attrs
