"""Real backends for the cache tests: kvdbclient's Bigtable emulator and its tables."""

# pylint: disable=redefined-outer-name
import uuid
from contextlib import suppress

import psutil
import pytest
from kvdbclient import BigTableClient, get_default_client_info
from kvdbclient_testing.bigtable.harness import harness


def _descendants() -> list[psutil.Process]:
    return psutil.Process().children(recursive=True)


@pytest.fixture(scope="session")
def emulator():
    """One emulator for the session, and nothing it started left running after.

    The harness signals only its `gcloud` wrapper, which leaves the `cbtemulator` that
    wrapper spawned alive; so every process the harness started is killed here.
    """
    if not harness.available():
        pytest.skip("no Bigtable emulator can start here")
    before = {proc.pid for proc in _descendants()}
    with harness.server() as host:
        spawned = [proc for proc in _descendants() if proc.pid not in before]
        yield host
    for proc in spawned:
        with suppress(psutil.NoSuchProcess):
            proc.kill()


def _client(prefix: str) -> BigTableClient:
    return BigTableClient(
        f"{prefix}_{uuid.uuid4().hex[:12]}", config=get_default_client_info().CONFIG
    )


@pytest.fixture
def graph(emulator):
    """An empty graph table; a test writes the parent rows it needs."""
    client = _client("graph")
    client.create_table(meta={"layer_count": 4}, version="test")
    return client


@pytest.fixture
def cache_id(emulator) -> str:
    """A cache table id no table holds yet."""
    return f"l2cache_{uuid.uuid4().hex[:12]}"
