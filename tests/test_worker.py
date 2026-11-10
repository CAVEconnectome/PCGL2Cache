"""The worker's per-chunk contract with the harness: write the chunk, then report it."""

import json
from types import SimpleNamespace

import cloudvolume.secrets
import numpy as np
from kvdbclient import BigTableClient, get_default_client_info

from helpers import link, local_volume, node_id
from pcgl2cache.pipeline.l2cache import setup, worker
from pcgl2cache.utils import atomic_chunk_bounds

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


def test_a_saved_info_opens_the_volume_without_its_server(tmp_path, monkeypatch):
    """The server's host never resolves, so any request to it would raise."""
    seg = np.zeros((32, 32, 8), dtype=np.uint64)
    seg[2:6, 2:6, 1:3] = SV
    info = {
        **local_volume(str(tmp_path / "ws"), seg).info,
        "data_dir": f"file://{tmp_path}/ws",
        "graph": {"chunk_size": [16, 16, 8]},
        "app": {"supported_api_versions": [0, 1]},
    }
    (tmp_path / "info.json").write_text(json.dumps(info))
    (tmp_path / "secrets").mkdir()
    (tmp_path / "secrets" / "cave-secret.json").write_text('{"token": "abc123"}')
    monkeypatch.setattr(cloudvolume.secrets, "CLOUD_VOLUME_DIR", str(tmp_path))
    path = "graphene://https://pcg.invalid/segmentation/table/g"
    monkeypatch.setenv("L2CACHE_CV_PATH", path)
    monkeypatch.setenv("L2CACHE_CV_INFO", str(tmp_path / "info.json"))
    cv = worker.open_volume()
    assert tuple(atomic_chunk_bounds(cv)) == (2, 2, 1)
    assert SV in np.unique(cv[0:16, 0:16, 0:8])
