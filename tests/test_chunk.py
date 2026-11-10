"""One chunk end to end: a real volume, its supervoxels resolved through a real graph."""

import numpy as np

from helpers import link, local_volume, node_id
from pcgl2cache.core.features import run_l2cache

SV_A1, SV_A2, SV_B = node_id(1, 10), node_id(1, 11), node_id(1, 12)
L2_A, L2_B = node_id(2, 1), node_id(2, 2)


def test_supervoxels_of_one_l2_land_in_one_row(tmp_path, graph):
    seg = np.zeros((32, 32, 8), dtype=np.uint64)
    seg[1:5, 1:5, 1:4] = SV_A1
    seg[5:8, 1:5, 1:4] = SV_A2
    seg[9:14, 9:14, 2:6] = SV_B
    link(graph, {SV_A1: L2_A, SV_A2: L2_A, SV_B: L2_B})
    out = run_l2cache(
        local_volume(tmp_path, seg), graph_client=graph, chunk_coord=(0, 0, 0)
    )
    sizes = dict(zip(out["l2id"].tolist(), out["size_nm3"].tolist()))
    assert sizes == {L2_A: 4 * 4 * 3 + 3 * 4 * 3, L2_B: 5 * 5 * 4}


def test_a_chunk_reads_only_its_own_slice(tmp_path, graph):
    seg = np.zeros((32, 16, 8), dtype=np.uint64)
    seg[20:24, 2:6, 1:3] = SV_A1  # in the second chunk along x
    link(graph, {SV_A1: L2_A})
    cv = local_volume(tmp_path, seg, chunk_size=(16, 16, 8), offset=(100, 0, 0))
    assert run_l2cache(cv, graph_client=graph, chunk_coord=(0, 0, 0)) == {}
    out = run_l2cache(cv, graph_client=graph, chunk_coord=(1, 0, 0))
    assert out["l2id"].tolist() == [L2_A]
    assert out["size_nm3"].tolist() == [4 * 4 * 2]
