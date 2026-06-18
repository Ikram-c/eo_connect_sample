import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Optional
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class SatelliteScene:
    id: str
    collection: str
    datetime: datetime
    cloud_cover: Optional[float]
    geometry: dict
    download_url: str
    thumbnail_url: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "collection": self.collection,
            "datetime": self.datetime.isoformat(),
            "cloud_cover": self.cloud_cover,
            "download_url": self.download_url,
        }


class CopernicusDataSpace:
    BASE_URL = "https://catalogue.dataspace.copernicus.eu/odata/v1"
    STAC_URL = "https://catalogue.dataspace.copernicus.eu/stac"
    AUTH_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"

    COLLECTIONS = {
        "sentinel-2": "SENTINEL-2",
        "sentinel-1": "SENTINEL-1",
        "sentinel-3-olci": "SENTINEL-3",
    }

    def __init__(self, username: str = None, password: str = None):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "EOSatelliteQuery/1.0"})
        self.authenticated = False
        if username and password:
            self._authenticate(username, password)

    def _authenticate(self, username: str, password: str):
        try:
            response = self.session.post(self.AUTH_URL, data={
                "client_id": "cdse-public",
                "username": username,
                "password": password,
                "grant_type": "password",
            })
            response.raise_for_status()
            token = response.json()["access_token"]
            self.session.headers.update({"Authorization": f"Bearer {token}"})
            self.authenticated = True
            logger.info("CDSE authentication successful")
        except Exception as e:
            logger.warning(f"CDSE authentication failed: {e}")

    def query_scenes(
        self,
        collection: str,
        bbox: tuple[float, float, float, float],
        start_date: datetime,
        end_date: datetime,
        max_cloud_cover: float = 30.0,
        limit: int = 50,
    ) -> list[SatelliteScene]:
        collection_name = self.COLLECTIONS.get(collection, collection)
        min_lon, min_lat, max_lon, max_lat = bbox

        filters = [
            f"Collection/Name eq '{collection_name}'",
            f"ContentDate/Start ge {start_date.isoformat()}Z",
            f"ContentDate/Start le {end_date.isoformat()}Z",
            (
                f"OData.CSC.Intersects(area=geography'SRID=4326;POLYGON(("
                f"{min_lon} {min_lat},{max_lon} {min_lat},{max_lon} {max_lat},"
                f"{min_lon} {max_lat},{min_lon} {min_lat}))')"
            ),
        ]

        if "sentinel-2" in collection.lower():
            filters.append(
                f"Attributes/OData.CSC.DoubleAttribute/any("
                f"att:att/Name eq 'cloudCover' and att/OData.CSC.DoubleAttribute/Value le {max_cloud_cover})"
            )

        query = f"{self.BASE_URL}/Products?$filter=" + " and ".join(filters)
        query += f"&$top={limit}&$orderby=ContentDate/Start desc"

        try:
            response = self.session.get(query, timeout=30)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            logger.error(f"CDSE query failed: {e}")
            return []

        scenes = []
        for item in data.get("value", []):
            cloud = None
            for attr in item.get("Attributes", []):
                if attr.get("Name") == "cloudCover":
                    cloud = attr.get("Value")
                    break
            scenes.append(SatelliteScene(
                id=item["Id"],
                collection=collection_name,
                datetime=datetime.fromisoformat(item["ContentDate"]["Start"].replace("Z", "")),
                cloud_cover=cloud,
                geometry=item.get("GeoFootprint", {}),
                download_url=f"{self.BASE_URL}/Products({item['Id']})/$value",
                thumbnail_url=(
                    item.get("Assets", [{}])[0].get("DownloadLink")
                    if item.get("Assets") else None
                ),
            ))

        return scenes

    def query_stac(
        self,
        collection: str,
        bbox: tuple[float, float, float, float],
        start_date: datetime,
        end_date: datetime,
        limit: int = 50,
    ) -> dict:
        payload = {
            "collections": [collection],
            "bbox": list(bbox),
            "datetime": f"{start_date.isoformat()}Z/{end_date.isoformat()}Z",
            "limit": limit,
        }
        response = self.session.post(f"{self.STAC_URL}/search", json=payload)
        response.raise_for_status()
        return response.json()


def compute_bbox(
    lat: float, lon: float, buffer_km: float = 50.0
) -> tuple[float, float, float, float]:
    lat_offset = buffer_km / 111.0
    lon_offset = buffer_km / (111.0 * max(0.1, abs(np.cos(np.radians(lat)))))
    return (lon - lon_offset, lat - lat_offset, lon + lon_offset, lat + lat_offset)


def query_availability(
    lat: float,
    lon: float,
    target_date: datetime,
    collections: list[str] = None,
    temporal_buffer_days: int = 1,
    spatial_buffer_km: float = 50.0,
    max_cloud_cover: float = 30.0,
    username: str = None,
    password: str = None,
) -> pd.DataFrame:
    if collections is None:
        collections = ["sentinel-2", "sentinel-1"]

    client = CopernicusDataSpace(username, password)
    bbox = compute_bbox(lat, lon, spatial_buffer_km)
    start = target_date - timedelta(days=temporal_buffer_days)
    end = target_date + timedelta(days=temporal_buffer_days)

    results = []
    for collection in collections:
        scenes = client.query_scenes(
            collection=collection,
            bbox=bbox,
            start_date=start,
            end_date=end,
            max_cloud_cover=max_cloud_cover,
        )
        for scene in scenes:
            time_diff = abs((scene.datetime - target_date).total_seconds() / 3600)
            results.append({
                "collection": collection,
                "scene_id": scene.id,
                "scene_datetime": scene.datetime,
                "time_diff_hours": round(time_diff, 2),
                "cloud_cover": scene.cloud_cover,
                "download_url": scene.download_url,
            })

    return pd.DataFrame(results)


def batch_query_from_csv(
    csv_path: str,
    collections: list[str] = None,
    temporal_buffer_days: int = 1,
    spatial_buffer_km: float = 50.0,
    max_cloud_cover: float = 30.0,
    username: str = None,
    password: str = None,
) -> pd.DataFrame:
    if collections is None:
        collections = ["sentinel-2", "sentinel-1"]

    df = pd.read_csv(csv_path)
    df["start_datetime"] = pd.to_datetime(
        df["Start date"].astype(str) + " " + df["Start time"].astype(str),
        dayfirst=True,
        errors="coerce",
    )
    for col in ["Start latitude", "Start longitude"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["start_datetime", "Start latitude", "Start longitude"])
    logger.info(f"Loaded {len(df)} records with valid coordinates")

    client = CopernicusDataSpace(username, password)
    results = []

    for idx, row in df.iterrows():
        lat, lon = row["Start latitude"], row["Start longitude"]
        dt = row["start_datetime"]
        bbox = compute_bbox(lat, lon, spatial_buffer_km)
        start = dt - timedelta(days=temporal_buffer_days)
        end = dt + timedelta(days=temporal_buffer_days)

        for collection in collections:
            try:
                scenes = client.query_scenes(
                    collection=collection,
                    bbox=bbox,
                    start_date=start,
                    end_date=end,
                    max_cloud_cover=max_cloud_cover,
                    limit=10,
                )
                for scene in scenes:
                    time_diff = abs((scene.datetime - dt).total_seconds() / 3600)
                    results.append({
                        "voyage_id": row.get("Id", idx),
                        "voyage_datetime": dt,
                        "voyage_lat": lat,
                        "voyage_lon": lon,
                        "camera_id": row.get("CameraId"),
                        "collection": collection,
                        "scene_id": scene.id,
                        "scene_datetime": scene.datetime,
                        "time_diff_hours": round(time_diff, 2),
                        "cloud_cover": scene.cloud_cover,
                        "download_url": scene.download_url,
                    })
            except Exception as e:
                logger.error(f"Error querying {collection} for row {idx}: {e}")

        if (idx + 1) % 10 == 0:
            logger.info(f"Processed {idx + 1}/{len(df)} records...")

    return pd.DataFrame(results)


if __name__ == "__main__":
    result = query_availability(
        lat=52.0,
        lon=4.5,
        target_date=datetime(2025, 7, 16, 12, 0),
        collections=["sentinel-2", "sentinel-1"],
        temporal_buffer_days=2,
        spatial_buffer_km=50.0,
        max_cloud_cover=30.0,
    )
    print(f"Found {len(result)} scenes")
    if not result.empty:
        print(result[["collection", "scene_datetime", "cloud_cover", "time_diff_hours"]])
        result.to_csv("satellite_availability.csv", index=False)