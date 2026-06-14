"""l2cache setup: create the cache Bigtable, stamping one snapshot timestamp that the whole
worker fleet reads back. Re-runnable — an existing table keeps its original stamp."""

import argparse
from datetime import datetime, timezone

from kvdbclient import BigTableClient, get_default_client_info
from pipeline.distribution import run_and_exit

import pcgl2cache

_TS_FORMAT = "%Y-%m-%d %H:%M:%S"


def create_cache_table(table_id: str, graph_id: str, cv_path: str) -> None:
    """Create the l2 cache table, stamping its meta with a snapshot timestamp of now;
    exist-ok so re-runs keep the original stamp the workers already read."""
    client = BigTableClient(table_id, config=get_default_client_info().CONFIG)
    now = datetime.now(timezone.utc).strftime(_TS_FORMAT)
    meta = {"graph_id": graph_id, "cv_path": cv_path, "timestamp": now}
    try:
        client.create_table(meta=meta, version=pcgl2cache.__version__)
    except ValueError:  # already exists -> keep its original snapshot timestamp
        pass


def main() -> int:
    parser = argparse.ArgumentParser(prog="pcgl2cache.pipeline.l2cache.setup")
    parser.add_argument("table_id")
    parser.add_argument("graph_id")
    parser.add_argument("cv_path")
    args = parser.parse_args()
    create_cache_table(args.table_id, args.graph_id, args.cv_path)
    return 0


if __name__ == "__main__":
    run_and_exit(main)
