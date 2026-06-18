from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class SatelliteScene:
    """
    Represents a standardized satellite scene retrieved from the API.
    """
    id: str
    collection: str
    datetime: datetime
    cloud_cover: Optional[float]
    geometry: dict
    download_url: str
    thumbnail_url: Optional[str] = None

    def to_dict(self) -> dict:
        """
        Converts the scene attributes into a flat dictionary representation.
        """
        return {
            "id": self.id,
            "collection": self.collection,
            "datetime": self.datetime.isoformat(),
            "cloud_cover": self.cloud_cover,
            "download_url": self.download_url,
        }