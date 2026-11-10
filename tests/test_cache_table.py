"""The cache table: setup's snapshot stamp, and worker rows as the API reads them."""

from datetime import datetime

import numpy as np
from kvdbclient import BigTableClient, get_default_client_info

from helpers import link, local_volume, node_id
from pcgl2cache.app.common import _attribute_name
from pcgl2cache.core.features import run_l2cache, write_to_db
from pcgl2cache.pipeline.l2cache import setup, worker

SV_A, SV_B = node_id(1, 10), node_id(1, 11)
L2_A, L2_B = node_id(2, 1), node_id(2, 2)

#: Each column the API serves, and the feature the worker writes into it.
SERVED = {
    "size_nm3": "size_nm3",
    "area_nm2": "area_nm2",
    "max_dt_nm": "max_dt_nm",
    "mean_dt_nm": "mean_dt_nm",
    "rep_coord_nm": "rep_coord_nm",
    "chunk_intersect_count": "chunk_intersect_count",
    "pca": "pca_comp",
    "pca_val": "pca_vals",
}


def _cache(table_id: str) -> BigTableClient:
    return BigTableClient(table_id, config=get_default_client_info().CONFIG)


def test_setup_stamps_a_snapshot_the_workers_parse(cache_id):
    setup.create_cache_table(cache_id, "graph", "file:///ws")
    stamp = _cache(cache_id).read_table_meta()["timestamp"]
    assert datetime.strptime(stamp, worker._TS_FORMAT)


def test_a_rerun_of_setup_keeps_the_first_snapshot(cache_id):
    """Every worker reads this one stamp, so a re-run must never move it."""
    first = {
        "graph_id": "graph",
        "cv_path": "file:///ws",
        "timestamp": "2020-01-01 00:00:00",
    }
    _cache(cache_id).create_table(meta=first, version="0")
    setup.create_cache_table(cache_id, "graph", "file:///ws")
    assert _cache(cache_id).read_table_meta()["timestamp"] == first["timestamp"]


def test_written_features_read_back_as_the_api_serves_them(tmp_path, graph, cache_id):
    seg = np.zeros((32, 32, 8), dtype=np.uint64)
    seg[1:3, 1:3, 1:2] = SV_A  # under the PCA floor, so its axes are empty
    seg[2:32, 4:30, 2:8] = SV_B
    link(graph, {SV_A: L2_A, SV_B: L2_B})
    cv = local_volume(tmp_path, seg)
    features = run_l2cache(cv, graph_client=graph, chunk_coord=(0, 0, 0))
    setup.create_cache_table(cache_id, "graph", "file:///ws")
    cache = _cache(cache_id)
    write_to_db(cache, features)
    rows = cache.read_nodes(node_ids=features["l2id"])
    for at, l2id in enumerate(features["l2id"]):
        cells = {
            _attribute_name(key): found[0].value for key, found in rows[l2id].items()
        }
        assert sorted(cells) == sorted(SERVED)
        for column, feature in SERVED.items():
            np.testing.assert_array_equal(cells[column], features[feature][at], column)
