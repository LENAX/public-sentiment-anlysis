""" This module contains domain models used and returned by core components and services.
"""

from .data_models import (
    DataModel,
    RequestHeader
)
from .spider_models import HTMLData, URL
from .parser_models import ParseResult
from .crawler_models import CrawlResult
from .job_models import JobData
from .weather_model import WeatherData
from .air_quality_model import AirQualityData
from .news_model import NewsData
from .covid_report_model import COVIDReportData
