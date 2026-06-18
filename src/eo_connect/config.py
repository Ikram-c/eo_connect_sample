from __future__ import annotations
import os
import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict, Any

_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config.yaml"


@dataclass(frozen=True)
class CopernicusEndpoints:
    """
    Configuration defaults for Copernicus Data Space Ecosystem network interactions.
    """
    base_url: str = "https://catalogue.dataspace.copernicus.eu/odata/v1"
    stac_url: str = "https://stac.dataspace.copernicus.eu/v1"
    auth_url: str = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
    client_id: str = "cdse-public"
    request_timeout_s: int = 30
    user_agent: str = "EOConnect/0.1.0"
    retry_total: int = 5
    retry_backoff_factor: float = 1.0
    retry_status_forcelist: List[int] = field(default_factory=lambda: [429, 500, 502, 503, 504])


@dataclass(frozen=True)
class QueryDefaults:
    """
    Default fallback parameters for spatial and temporal queries.
    """
    max_cloud_cover_pct: float = 30.0
    temporal_buffer_days: int = 1
    spatial_buffer_km: float = 50.0
    result_limit: int = 50
    batch_result_limit: int = 10
    batch_log_interval: int = 10
    batch_chunk_size: int = 1000


@dataclass(frozen=True)
class GeometryConstants:
    """
    Mathematical constants for spatial coordinate calculation and boundary mapping.
    """
    km_per_degree_lat: float = 111.0
    min_cos_clamp: float = 0.1
    min_lat: float = -90.0
    max_lat: float = 90.0
    min_lon: float = -180.0
    max_lon: float = 180.0
    lon_wrap: float = 360.0


@dataclass(frozen=True)
class CSVColumns:
    """
    Default column header mappings for parsing input files.
    """
    date: str = "Start date"
    time: str = "Start time"
    latitude: str = "Start latitude"
    longitude: str = "Start longitude"
    id: str = "Id"
    camera_id: str = "CameraId"


@dataclass(frozen=True)
class GUIDefaults:
    """
    Default boundary and presentation values for user interface rendering.
    """
    default_lat: float = 52.0
    default_lon: float = 4.5
    max_buffer_days: int = 30
    max_buffer_km: float = 500.0
    min_window_width: int = 900
    min_window_height: int = 700


@dataclass(frozen=True)
class Credentials:
    """
    Authentication payloads populated strictly from environment variables.
    """
    username: Optional[str] = field(default_factory=lambda: os.environ.get("CDSE_USERNAME"))
    password: Optional[str] = field(default_factory=lambda: os.environ.get("CDSE_PASSWORD"))


@dataclass(frozen=True)
class AppConfig:
    """
    Root configuration composite mapping YAML declarations to dataclass hierarchies.
    """
    copernicus: CopernicusEndpoints = field(default_factory=CopernicusEndpoints)
    query_defaults: QueryDefaults = field(default_factory=QueryDefaults)
    geometry: GeometryConstants = field(default_factory=GeometryConstants)
    collections: Dict[str, str] = field(default_factory=lambda: {
        "sentinel-2": "SENTINEL-2",
        "sentinel-1": "SENTINEL-1",
        "sentinel-3-olci": "SENTINEL-3",
    })
    csv_columns: CSVColumns = field(default_factory=CSVColumns)
    gui_defaults: GUIDefaults = field(default_factory=GUIDefaults)
    credentials: Credentials = field(default_factory=Credentials)


def _build_dataclass(cls: Any, data: dict) -> Any:
    """
    Instantiates a dataclass filtering strictly mapped initialization arguments.
    """
    if data is None:
        return cls()
    filtered = {k: v for k, v in data.items() if k in {f.name for f in cls.__dataclass_fields__.values()}}
    return cls(**filtered)


def load_config(path: Optional[Path] = None) -> AppConfig:
    """
    Parses application constants from the configuration file safely.
    """
    path = Path(path) if path else _DEFAULT_CONFIG_PATH
    if not path.exists():
        return AppConfig()
    with open(path) as f:
        raw = yaml.safe_load(f) or {}
    return AppConfig(
        copernicus=_build_dataclass(CopernicusEndpoints, raw.get("copernicus")),
        query_defaults=_build_dataclass(QueryDefaults, raw.get("query_defaults")),
        geometry=_build_dataclass(GeometryConstants, raw.get("geometry")),
        collections=raw.get("collections", AppConfig.collections),
        csv_columns=_build_dataclass(CSVColumns, raw.get("csv_columns")),
        gui_defaults=_build_dataclass(GUIDefaults, raw.get("gui_defaults")),
        credentials=Credentials(),
    )