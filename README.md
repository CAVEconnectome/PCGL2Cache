# pcgl2cache

Cache of per-L2-chunk statistics for [PyChunkedGraph](https://github.com/CAVEconnectome/PyChunkedGraph)
proofreading datasets. Computes geometric features over a graph's layer-2
nodes and serves them via HTTP for downstream tools (proofreading clients,
analysis notebooks, automated pipelines).

## What it caches

Per L2 node:

| Attribute | Type | Meaning |
|---|---|---|
| `size_nm3` | uint32 | Volume in nm³ |
| `area_nm2` | uint32 | Surface area in nm² (overlap-shift estimate) |
| `max_dt_nm`, `mean_dt_nm` | uint16 / float16 | Stats from the Euclidean distance transform |
| `rep_coord_nm` | uint16[3] | Distance-weighted representative coordinate |
| `chunk_intersect_count` | uint16[N, 3] | Boundary intersections per axis |
| `pca`, `pca_val` | float16[N, 3] / float32[N] | 3D PCA components and singular values |

All values are computed once from the segmentation volume at L2 chunk
granularity and read back by ID.

## Architecture

Three roles share a single image (entrypoint chosen at deploy time):

- **Frontend** (Flask + uwsgi) — `POST /l2cache/api/v1/table/<dataset>/attributes`
  returns cached attributes for a list of L2 IDs, with optional async
  recompute of any missing IDs via a messaging-bus payload.
- **Batch ingest** (`flask cli ingest …`) — initial bulk build:
  enumerates the atomic chunk grid from the graph's CloudVolume bounds,
  enqueues per-chunk jobs into Redis/RQ, workers compute features and
  write to BigTable.
- **Update workers** (`messagingclient` consumers in [`workers/`](workers/))
  — react to graph edits by recomputing cache entries for the affected
  L2 IDs.

Storage is BigTable, accessed via [kvdbclient](https://github.com/seung-lab/kvdbclient).
The frontend talks to PyChunkedGraph through a `graphene://` CloudVolume
URL (version-agnostic). Batch ingest reads the graph table directly via
`kvdbclient.RootExtension`, which auto-detects the layer schema for both
pcgv1 and pcgv2 graphs.

## Configuration

A YAML file maps each dataset to its graphene URL and L2 cache table:

```yaml
fly_v31:
  cv_path: "graphene://https://prodv1.flywire-daf.com/segmentation/1.0/fly_v31"
  l2cache_id: "l2cache_fly_v31_v2"
minnie3_v1:
  cv_path: "graphene://https://minniev1.microns-daf.com/segmentation/table/minnie3_v1"
  l2cache_id: "l2cache_minnie3_v1_v1"
```

Path is provided via `GRAPH_L2CACHE_CONFIG_PATH`.

Other environment variables:

- `BIGTABLE_PROJECT`, `BIGTABLE_INSTANCE` — kvdbclient backend (see kvdbclient docs)
- `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD` — RQ broker
- `L2CACHE_EXCHANGE` — messaging exchange used for async recompute
  triggers (default: `pychunkedgraph`)
- `L2JOB_BATCH_SIZE` — RQ enqueue batch size for ingest (default: `10000`)
- `JOB_TIMEOUT` — per-chunk worker timeout (default: `5m`)

## HTTP API

Mounted at `/l2cache/api/v1`. All routes require `view` permission via
[middle-auth-client](https://github.com/seung-lab/middle_auth_client).

| Method | Path | Purpose |
|---|---|---|
| `GET`  | `/attribute_metadata` | List registered attribute names + dtypes |
| `POST` | `/table/<dataset>/attributes` | Bulk lookup (body: `{"l2_ids": [...]}` or raw uint64 buffer) |
| `GET`  | `/table_mapping` | Return the dataset → cache YAML config |

Query parameters on `/attributes`:

- `attribute_names` — comma-separated subset of attributes to return
- `int64_as_str` — emit uint64 fields as strings (for JSON consumers)
- `update_cache` — when `false`, skip the async recompute trigger for
  missing IDs (default: `true`)

Coordinates returned in `rep_coord_nm` are absolute, world-space
nanometers (chunk-relative offsets in storage are added to the chunk's
world origin before serialization).

## Batch ingest

Build a fresh L2 cache table (graph schema auto-detected):

```bash
flask cli ingest <cache_id> <graph_id> <cv_path> "<timestamp>" --create
```

- `--create` provisions the BigTable.
- `--test` queues 8 chunks at the dataset center for a smoke run.
- Worker pool: `rq worker l2 -c pcgl2cache.config.DeploymentWithRedisConfig`
  (or run inside the same image with `flask cli rq …` subcommands; see
  `pcgl2cache.ingest.rq_cli`).
- Progress: `flask cli ingest status` prints `<completed>/<total>`.

## Installation

Local install:

```bash
pip install -e .
```

Requires Python 3.11+, Redis (for ingest only), and a BigTable instance
or emulator. Heavy compute deps (`edt`, `fastremap`, `scikit-learn`,
`numpy`) are pure pip wheels.

## Docker

Single image for all three roles:

```bash
DOCKER_BUILDKIT=1 docker build -t pcgl2cache:dev .
```

The frontend, ingest CLI, and update workers all run from this image
with role-specific entrypoints supplied by your deployment manifest.

## Release

Versioned like PyChunkedGraph: a committed `pcgl2cache/_version.py` literal, bumped by a one-click
workflow — no manual edit or `bumpversion`.

- **Release:** Actions → **publish release** → **Run workflow** → choose `part`
  (`major`/`minor`/`patch`), or `gh workflow run release.yml -f part=patch`. It bumps `_version.py`,
  commits, tags `vX.Y.Z`, and creates a GitHub Release; the existing Cloud Build trigger builds the
  image from the tag.
- **Preview:** `dry-run=true` prints the next version without committing or tagging.

## License

GPL-3.0 — see [LICENSE](LICENSE).
