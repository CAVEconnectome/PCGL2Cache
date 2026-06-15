"""l2cache setup: create the cache Bigtable (stamping one snapshot timestamp the whole
worker fleet reads back) and, when configured, register the graph with CAVE auth so its
graphene CV is readable. Re-runnable — an existing table keeps its original stamp."""

import argparse
import logging
from datetime import datetime, timezone

import requests
from cloudvolume.secrets import cave_credentials
from kvdbclient import BigTableClient, get_default_client_info
from cave_pipeline.distribution import run_and_exit

import pcgl2cache

logger = logging.getLogger(__name__)
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


def add_service_mapping(table_name: str, server_host: str, dataset: str, service: str) -> None:
    """Register the graph with CAVE auth (sticky_auth) so its graphene CV is readable —
    without it the CV crashes with an auth error, notably right after ingest."""
    token = str(cave_credentials()["token"])
    mapping = f"api/v1/service/{service}/table/{table_name}/dataset/{dataset}"
    url = f"{server_host}/sticky_auth/{mapping}"
    response = requests.post(url, headers={"Authorization": f"Bearer {token}"}, timeout=15)
    logger.info(f"cave service mapping {response.status_code}: {url}")
    response.raise_for_status()  # fail setup if unregistered — else the CV auth-crashes


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(prog="pcgl2cache.pipeline.l2cache.setup")
    parser.add_argument("table_id")
    parser.add_argument("graph_id")
    parser.add_argument("cv_path")
    parser.add_argument("--cave-host")
    parser.add_argument("--cave-dataset")
    parser.add_argument("--cave-service")
    args = parser.parse_args()
    create_cache_table(args.table_id, args.graph_id, args.cv_path)
    if args.cave_host:  # CAVE auth registration is opt-in (skipped for public CVs)
        add_service_mapping(
            args.graph_id, args.cave_host, args.cave_dataset, args.cave_service
        )
    return 0


if __name__ == "__main__":
    run_and_exit(main)
