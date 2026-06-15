"""l2cache worker: compute + write the L2 feature cache for a batch of chunks.

Plugged into cave-pipeline's harness — one pchunkedgraph-free pod per JOB_COMPLETION_INDEX,
working against any pcg version via kvdbclient. The snapshot timestamp is read from the cache
table's meta (recorded once at setup), so the whole fleet shares it; writes are idempotent
(by l2 id), so no per-chunk lock.
"""

import logging
import os
from datetime import datetime, timezone
from types import SimpleNamespace

import numpy as np
from cloudvolume import CloudVolume
from kvdbclient import BigTableClient, get_default_client_info
from cave_pipeline.distribution.harness import run

from ...core.features import run_l2cache, write_to_db
from ...utils import atomic_chunk_bounds, get_graph_client

logger = logging.getLogger(__name__)
_TS_FORMAT = "%Y-%m-%d %H:%M:%S"


def context_factory(env):
    """Per-pod state, built once: segmentation volume, cache + graph clients, the shared
    snapshot timestamp from the cache meta, and the L2 chunk grid."""
    config = get_default_client_info().CONFIG
    cv = CloudVolume(
        os.environ["L2CACHE_CV_PATH"], bounded=False, fill_missing=True, progress=False
    )
    cache_client = BigTableClient(os.environ["L2CACHE_TABLE_ID"], config=config)
    ts = cache_client.read_table_meta()["timestamp"]  # one snapshot for the whole fleet
    return SimpleNamespace(
        cv=cv,
        cache_client=cache_client,
        graph_client=get_graph_client(env["graph_id"]),
        timestamp=datetime.strptime(ts, _TS_FORMAT).replace(tzinfo=timezone.utc),
        bounds=tuple(int(b) for b in atomic_chunk_bounds(cv)),
    )


def bounds_fn(ctx, layer):
    return ctx.bounds


def make_processor(ctx, layer, env):
    def process_one(coord):
        try:
            features = run_l2cache(
                ctx.cv,
                graph_client=ctx.graph_client,
                chunk_coord=np.array(coord, dtype=int),
                timestamp=ctx.timestamp,
            )
            if features:  # empty chunk -> nothing to write
                write_to_db(ctx.cache_client, features)
            return "ok"
        except Exception:
            logger.exception(f"l2cache failure on chunk {tuple(coord)}")
            return "transient"

    return process_one


def main() -> int:
    return run(make_processor, context_factory=context_factory, bounds_fn=bounds_fn)
