"""A chunk's L2 features, computed from its contiguously labelled segmentation."""

import numpy as np

from helpers import RESOLUTION, node_id
from pcgl2cache.core.features import calculate_features

SHAPE = (32, 32, 8)
L2_A, L2_B = node_id(2, 1), node_id(2, 2)


def _features(seg: np.ndarray) -> dict[str, np.ndarray]:
    """The features of `seg`, whose labels 1 and 2 stand for `L2_A` and `L2_B`."""
    return calculate_features(seg, {1: L2_A, 2: L2_B}, np.array(RESOLUTION))


def test_area_sums_each_face_by_its_area_in_nm2():
    seg = np.zeros(SHAPE, dtype=np.uint32)
    seg[2:6, 3:8, 1:4] = 1  # 4 x 5 x 3 voxels, clear of every chunk face
    x, y, z = RESOLUTION
    faces = 2 * (5 * 3 * y * z + 4 * 3 * x * z + 4 * 5 * x * y)
    assert _features(seg)["area_nm2"].tolist() == [faces]


def test_pca_is_empty_below_a_hundredth_of_a_cubic_micron():
    """3907 voxels of 2560 nm3 reach 0.01 um3; below that the axes stay empty."""
    seg = np.zeros(SHAPE, dtype=np.uint32)
    seg[1:3, 1:3, 1:2] = 1  # 4 voxels
    seg[2:32, 4:30, 2:8] = 2  # 4680 voxels
    out = _features(seg)
    rows = zip(out["l2id"].tolist(), out["pca_comp"], out["pca_vals"])
    shapes = {l2id: (comp.shape, vals.shape) for l2id, comp, vals in rows}
    assert shapes == {L2_A: ((0, 3), (0,)), L2_B: ((3, 3), (3,))}
