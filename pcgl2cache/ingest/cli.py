"""
cli for running ingest
"""

from datetime import datetime
from datetime import timezone

import click
import numpy as np
from cloudvolume import CloudVolume
from flask.cli import AppGroup
from kvdbclient import BigTableClient
from kvdbclient import get_default_client_info

import pcgl2cache
from . import IngestConfig
from . import ClusterIngestConfig
from .jobs import enqueue_atomic_tasks
from .manager import IngestManager
from ..utils import atomic_chunk_bounds
from .redis import get_redis_connection
from .redis import keys as r_keys

ingest_cli = AppGroup("ingest")


@ingest_cli.command("flush_redis")
def flush_redis():
    """FLush redis db."""
    redis = get_redis_connection()
    redis.flushdb()


@ingest_cli.command("ingest")
@click.argument("cache_id", type=str)
@click.argument("graph_id", type=str)
@click.argument("cv_path", type=str)
@click.argument("timestamp", type=str)
@click.option("--create", is_flag=True, help="Creates a bigtable named CACHE_ID.")
@click.option(
    "--test", is_flag=True, help="Queues 8 chunks at the center of the dataset."
)
def ingest_cache(
    cache_id: str,
    graph_id: str,
    cv_path: str,
    timestamp: str,
    create: bool,
    test: bool,
):
    """Main ingest command. Works against any pcg version (kvdbclient
    auto-detects layer count from the graph's bigtable meta)."""
    if create:
        meta = {"graph_id": graph_id, "cv_path": cv_path, "timestamp": timestamp}
        client = BigTableClient(cache_id, config=get_default_client_info().CONFIG)
        client.create_table(meta=meta, version=pcgl2cache.__version__)

    timestamp = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S").replace(
        tzinfo=timezone.utc
    )
    enqueue_atomic_tasks(
        IngestManager(
            IngestConfig(CLUSTER=ClusterIngestConfig(), TEST_RUN=test),
            cache_id,
            graph_id,
            cv_path,
        ),
        cv_path,
        timestamp,
    )


@ingest_cli.command("status")
def ingest_status():
    """Print progress completed/total."""
    redis = get_redis_connection()
    imanager = IngestManager.from_pickle(redis.get(r_keys.INGESTION_MANAGER))
    cv = CloudVolume(imanager.cv_path)
    l2chunk_count = int(np.prod(atomic_chunk_bounds(cv)))
    print(f"{redis.scard('2c')} / {l2chunk_count}")


def init_ingest_cmds(app):
    app.cli.add_command(ingest_cli)
