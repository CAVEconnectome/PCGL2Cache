"""Builders for the real rows and volumes the cache tests run on."""

import numpy as np
from cloudvolume import CloudVolume
from kvdbclient import BigTableClient
from kvdbclient.attributes import Hierarchy
from kvdbclient.base import serialize_uint64

RESOLUTION = (8, 8, 40)
LAYER_BITS = 8


def node_id(layer: int, segment: int) -> int:
    """A node id in chunk (0, 0, 0) of `layer`, the layer held in the top bits."""
    return layer << (64 - LAYER_BITS) | segment


def link(graph: BigTableClient, parents: dict[int, int]) -> None:
    """Write each supervoxel's parent row, as an ingested graph holds it."""
    graph.write(
        [
            graph.mutate_row(
                serialize_uint64(sv), {Hierarchy.Parent: np.uint64(parent)}
            )
            for sv, parent in parents.items()
        ]
    )


def local_volume(
    path: str, seg: np.ndarray, chunk_size=None, offset=(0, 0, 0)
) -> CloudVolume:
    """`seg` as a precomputed layer on disk, with the graph chunk size graphene serves."""
    cv = CloudVolume.from_numpy(
        seg,
        vol_path=f"file://{path}",
        resolution=RESOLUTION,
        voxel_offset=offset,
        chunk_size=seg.shape if chunk_size is None else chunk_size,
        layer_type="segmentation",
    )
    # A precomputed layer has no graph; graphene's info carries this in production.
    cv.graph_chunk_size = np.array(seg.shape if chunk_size is None else chunk_size)
    return cv
