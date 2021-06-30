from pydantic import BaseModel
from typing import Optional
from uuid import UUID
from datetime import date
from ..db_models import AirQuality as AirQualityDBModel


class AirQualityData(BaseModel):
    """ Defines an air quality record
  
    """
    air_quality_id: Optional[UUID]
    title: Optional[str] = ""
    province: Optional[str] = ""
    city: Optional[str] = ""
    date: Optional[date]
    quality: Optional[str] = ""
    AQI: Optional[str] = ""
    AQI_rank: Optional[str] = ""
    PM25: Optional[str] = ""
    PM10: Optional[str] = ""
    SO2: Optional[str] = ""
    NO2: Optional[str] = ""
    Co: Optional[str] = ""
    O3: Optional[str] = ""

    remark: Optional[str] = ""

    def __hash__(self):
        return hash(self.__repr__())

    @classmethod
    def from_db_model(cls, model_instance: AirQualityDBModel) -> "AirQualityData":
        return cls.parse_obj(model_instance)

    def to_db_model(self) -> "AirQualityData":
        pass
