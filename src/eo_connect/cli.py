from __future__ import annotations
import argparse
import logging
from datetime import datetime
from pathlib import Path

from .config import load_config
from .query import query_availability, batch_query_from_csv

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def main() -> None:
    """
    Command line interface parser exposing internal tool functionalities for headless access.
    """
    parser = argparse.ArgumentParser(description="EO Connect - Satellite imagery query tool")
    parser.add_argument("--config", type=Path, default=None)
    sub = parser.add_subparsers(dest="command", required=True)

    p_query = sub.add_parser("query")
    p_query.add_argument("--lat", type=float, required=True)
    p_query.add_argument("--lon", type=float, required=True)
    p_query.add_argument("--date", type=str, required=True)
    p_query.add_argument("--collections", nargs="+", default=None)
    p_query.add_argument("--cloud-cover", type=float, default=None)
    p_query.add_argument("--buffer-days", type=int, default=None)
    p_query.add_argument("--buffer-km", type=float, default=None)
    p_query.add_argument("--output", type=Path, default=None)
    p_query.add_argument("--username", type=str, default=None)
    p_query.add_argument("--password", type=str, default=None)

    p_batch = sub.add_parser("batch")
    p_batch.add_argument("csv", type=Path)
    p_batch.add_argument("--collections", nargs="+", default=None)
    p_batch.add_argument("--cloud-cover", type=float, default=None)
    p_batch.add_argument("--buffer-days", type=int, default=None)
    p_batch.add_argument("--buffer-km", type=float, default=None)
    p_batch.add_argument("--output", type=Path, default=None)
    p_batch.add_argument("--username", type=str, default=None)
    p_batch.add_argument("--password", type=str, default=None)

    args = parser.parse_args()
    cfg = load_config(args.config) if args.config else load_config()

    if args.command == "query":
        target = datetime.fromisoformat(args.date)
        df = query_availability(
            lat=args.lat, lon=args.lon, target_date=target,
            collections=args.collections,
            temporal_buffer_days=args.buffer_days,
            spatial_buffer_km=args.buffer_km,
            max_cloud_cover=args.cloud_cover,
            username=args.username, password=args.password,
            config=cfg,
        )
        print(f"Found {len(df)} scenes")
        if not df.empty:
            print(df[["collection", "scene_datetime", "cloud_cover", "time_diff_hours"]])
        if args.output:
            df.to_csv(args.output, index=False)
            print(f"Saved to {args.output}")

    elif args.command == "batch":
        df = batch_query_from_csv(
            csv_path=str(args.csv),
            collections=args.collections,
            temporal_buffer_days=args.buffer_days,
            spatial_buffer_km=args.buffer_km,
            max_cloud_cover=args.cloud_cover,
            username=args.username, password=args.password,
            config=cfg,
        )
        out = args.output or Path("satellite_availability.csv")
        df.to_csv(out, index=False)
        print(f"Saved {len(df)} results to {out}")


if __name__ == "__main__":
    main()