from __future__ import annotations
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import logging
from datetime import datetime
from typing import Optional, List, Tuple

from .config import AppConfig, load_config
from .models import SatelliteScene

logger = logging.getLogger(__name__)


class CopernicusDataSpace:
    """
    Stateful HTTP client mapped to the Copernicus Data Space Ecosystem.
    """

    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        config: Optional[AppConfig] = None,
    ):
        self.cfg = config or load_config()
        ep = self.cfg.copernicus
        self.session = requests.Session()

        retry = Retry(
            total=ep.retry_total,
            backoff_factor=ep.retry_backoff_factor,
            status_forcelist=ep.retry_status_forcelist,
            allowed_methods=["GET", "POST"]
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        self.session.headers.update({"User-Agent": ep.user_agent})
        self.authenticated = False
        u = username or self.cfg.credentials.username
        p = password or self.cfg.credentials.password
        if u and p:
            self._authenticate(u, p)

    def _authenticate(self, username: str, password: str) -> None:
        """
        Procures OAuth2 access tokens executing standard password grants.
        """
        ep = self.cfg.copernicus
        try:
            resp = self.session.post(ep.auth_url, data={
                "client_id": ep.client_id,
                "username": username,
                "password": password,
                "grant_type": "password",
            })
            resp.raise_for_status()
            token = resp.json()["access_token"]
            self.session.headers.update({"Authorization": f"Bearer {token}"})
            self.authenticated = True
            logger.info("CDSE authentication successful")
        except Exception as e:
            logger.error(f"CDSE authentication failed: {e}")
            raise

    def query_scenes(
        self,
        collection: str,
        bbox: Tuple[float, float, float, float],
        start_date: datetime,
        end_date: datetime,
        max_cloud_cover: Optional[float] = None,
        limit: Optional[int] = None,
    ) -> List[SatelliteScene]:
        """
        Discovers satellite acquisitions utilizing normalized OData spatial filters.
        """
        qd = self.cfg.query_defaults
        max_cc = max_cloud_cover if max_cloud_cover is not None else qd.max_cloud_cover_pct
        lim = limit or qd.result_limit
        collection_name = self.cfg.collections.get(collection, collection)
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
                f"att:att/Name eq 'cloudCover' and att/OData.CSC.DoubleAttribute/Value le {max_cc})"
            )

        url = f"{self.cfg.copernicus.base_url}/Products?$filter=" + " and ".join(filters)
        url += f"&$top={lim}&$orderby=ContentDate/Start desc"

        try:
            resp = self.session.get(url, timeout=self.cfg.copernicus.request_timeout_s)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error(f"CDSE query failed: {e}")
            raise

        return [self._parse_scene(item, collection_name) for item in data.get("value", [])]

    def query_stac(
        self,
        collection: str,
        bbox: Tuple[float, float, float, float],
        start_date: datetime,
        end_date: datetime,
        limit: Optional[int] = None,
    ) -> dict:
        """
        Yields STAC collection payloads for specific spatio-temporal bounds.
        """
        lim = limit or self.cfg.query_defaults.result_limit
        payload = {
            "collections": [collection],
            "bbox": list(bbox),
            "datetime": f"{start_date.isoformat()}Z/{end_date.isoformat()}Z",
            "limit": lim,
        }
        resp = self.session.post(f"{self.cfg.copernicus.stac_url}/search", json=payload)
        resp.raise_for_status()
        return resp.json()

    def _parse_scene(self, item: dict, collection_name: str) -> SatelliteScene:
        """
        Maps nested vendor payloads into the standardized scene model.
        """
        cloud = None
        for attr in item.get("Attributes", []):
            if attr.get("Name") == "cloudCover":
                cloud = attr.get("Value")
                break
        assets = item.get("Assets", [])
        return SatelliteScene(
            id=item["Id"],
            collection=collection_name,
            datetime=datetime.fromisoformat(item["ContentDate"]["Start"].replace("Z", "")),
            cloud_cover=cloud,
            geometry=item.get("GeoFootprint", {}),
            download_url=f"{self.cfg.copernicus.base_url}/Products({item['Id']})/$value",
            thumbnail_url=assets[0].get("DownloadLink") if assets else None,
        )