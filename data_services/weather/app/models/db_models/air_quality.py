from ..data_models import AirQuality
from .db_model import DBModel
from uuid import UUID, uuid5, NAMESPACE_OID
from datetime import datetime
from typing import Optional
from pydantic import Field


class AirQualityDBModel(DBModel, AirQuality):
    __collection__: str = "AirQuality"
    air_quality_id: Optional[UUID] = Field(default_factory=lambda: uuid5(
        NAMESPACE_OID, f"AQI_{datetime.now().timestamp()}"))