from __future__ import annotations
import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, List, Tuple

from .config import AppConfig, load_config
from .client import CopernicusDataSpace

logger = logging.getLogger(__name__)


def compute_bbox(
    lat: float,
    lon: float,
    buffer_km: float,
    config: Optional[AppConfig] = None,
) -> Tuple[float, float, float, float]:
    """
    Synthesizes geographical bounding boxes correcting for Earth surface topology.
    """
    cfg = config or load_config()
    g = cfg.geometry
    lat_offset = buffer_km / g.km_per_degree_lat
    lon_offset = buffer_km / (g.km_per_degree_lat * max(g.min_cos_clamp, abs(np.cos(np.radians(lat)))))

    min_lon = (lon - lon_offset - g.min_lon) % g.lon_wrap + g.min_lon
    max_lon = (lon + lon_offset - g.min_lon) % g.lon_wrap + g.min_lon
    min_lat = max(g.min_lat, lat - lat_offset)
    max_lat = min(g.max_lat, lat + lat_offset)

    if min_lon > max_lon:
        min_lon, max_lon = max_lon, min_lon

    return (min_lon, min_lat, max_lon, max_lat)


def query_availability(
    lat: float,
    lon: float,
    target_date: datetime,
    collections: Optional[List[str]] = None,
    temporal_buffer_days: Optional[int] = None,
    spatial_buffer_km: Optional[float] = None,
    max_cloud_cover: Optional[float] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    config: Optional[AppConfig] = None,
) -> pd.DataFrame:
    """
    Executes a singular localized search compiling data matching strict tolerances.
    """
    cfg = config or load_config()
    qd = cfg.query_defaults
    collections = collections or ["sentinel-2", "sentinel-1"]
    tb = temporal_buffer_days if temporal_buffer_days is not None else qd.temporal_buffer_days
    sb = spatial_buffer_km if spatial_buffer_km is not None else qd.spatial_buffer_km
    mc = max_cloud_cover if max_cloud_cover is not None else qd.max_cloud_cover_pct

    client = CopernicusDataSpace(username, password, config=cfg)
    bbox = compute_bbox(lat, lon, sb, config=cfg)
    start = target_date - timedelta(days=tb)
    end = target_date + timedelta(days=tb)

    results = []
    for collection in collections:
        scenes = client.query_scenes(
            collection=collection, bbox=bbox,
            start_date=start, end_date=end, max_cloud_cover=mc,
        )
        for s in scenes:
            time_diff = abs((s.datetime - target_date).total_seconds() / 3600)
            results.append({
                "collection": collection,
                "scene_id": s.id,
                "scene_datetime": s.datetime,
                "time_diff_hours": round(time_diff, 2),
                "cloud_cover": s.cloud_cover,
                "download_url": s.download_url,
            })
    return pd.DataFrame(results)


def batch_query_from_csv(
    csv_path: str,
    collections: Optional[List[str]] = None,
    temporal_buffer_days: Optional[int] = None,
    spatial_buffer_km: Optional[float] = None,
    max_cloud_cover: Optional[float] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    config: Optional[AppConfig] = None,
) -> pd.DataFrame:
    """
    Iterates chunked payload documents issuing queries for localized trajectories.
    """
    cfg = config or load_config()
    qd = cfg.query_defaults
    col = cfg.csv_columns
    collections = collections or ["sentinel-2", "sentinel-1"]
    tb = temporal_buffer_days if temporal_buffer_days is not None else qd.temporal_buffer_days
    sb = spatial_buffer_km if spatial_buffer_km is not None else qd.spatial_buffer_km
    mc = max_cloud_cover if max_cloud_cover is not None else qd.max_cloud_cover_pct

    client = CopernicusDataSpace(username, password, config=cfg)
    results = []

    chunk_iter = pd.read_csv(csv_path, chunksize=qd.batch_chunk_size)

    for chunk_idx, df in enumerate(chunk_iter):
        df["start_datetime"] = pd.to_datetime(
            df[col.date].astype(str) + " " + df[col.time].astype(str),
            dayfirst=True, errors="coerce",
        )
        for c in [col.latitude, col.longitude]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df = df.dropna(subset=["start_datetime", col.latitude, col.longitude])

        for idx, row in df.iterrows():
            lat, lon = row[col.latitude], row[col.longitude]
            dt = row["start_datetime"]
            bbox = compute_bbox(lat, lon, sb, config=cfg)
            start = dt - timedelta(days=tb)
            end = dt + timedelta(days=tb)

            for collection in collections:
                try:
                    scenes = client.query_scenes(
                        collection=collection, bbox=bbox,
                        start_date=start, end_date=end,
                        max_cloud_cover=mc, limit=qd.batch_result_limit,
                    )
                    for s in scenes:
                        time_diff = abs((s.datetime - dt).total_seconds() / 3600)
                        results.append({
                            "voyage_id": row.get(col.id, idx),
                            "voyage_datetime": dt,
                            "voyage_lat": lat,
                            "voyage_lon": lon,
                            "camera_id": row.get(col.camera_id),
                            "collection": collection,
                            "scene_id": s.id,
                            "scene_datetime": s.datetime,
                            "time_diff_hours": round(time_diff, 2),
                            "cloud_cover": s.cloud_cover,
                            "download_url": s.download_url,
                        })
                except Exception as e:
                    logger.error(f"Error querying {collection} for row {idx}: {e}")

            if (idx + 1) % qd.batch_log_interval == 0:
                logger.info(f"Processed {idx + 1} records in chunk {chunk_idx + 1}...")

    return pd.DataFrame(results)