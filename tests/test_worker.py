"""The worker's per-chunk contract with the harness: write the chunk, then report it."""

from types import SimpleNamespace

import numpy as np
from kvdbclient import BigTableClient, get_default_client_info

from helpers import link, local_volume, node_id
from pcgl2cache.pipeline.l2cache import setup, worker

SV, L2 = node_id(1, 10), node_id(2, 1)


def _process(tmp_path, graph, cache_id: str):
    """The processor for one chunk holding a single L2 object, and its cache client."""
    seg = np.zeros((16, 16, 8), dtype=np.uint64)
    seg[2:6, 2:6, 1:3] = SV
    link(graph, {SV: L2})
    cache = BigTableClient(cache_id, config=get_default_client_info().CONFIG)
    ctx = SimpleNamespace(
        cv=local_volume(tmp_path, seg),
        graph_client=graph,
        cache_client=cache,
        timestamp=None,
    )
    return worker.make_processor(ctx, 2, {}), cache


def test_a_written_chunk_reports_ok(tmp_path, graph, cache_id):
    setup.create_cache_table(cache_id, "graph", "file:///ws")
    process, cache = _process(tmp_path, graph, cache_id)
    assert process((0, 0, 0)) == "ok"
    assert list(cache.read_nodes(node_ids=[np.uint64(L2)])) == [L2]


def test_a_chunk_whose_write_fails_reports_transient(tmp_path, graph, cache_id):
    """No cache table exists here, so the write fails."""
    process, _ = _process(tmp_path, graph, cache_id)
    assert process((0, 0, 0)) == "transient"
