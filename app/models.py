from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class SearchRequest(BaseModel):
    origin_city: str
    destination_city: str
    departure_date: date
    max_price: int | None = None
    departure_time_filters: list[str] = Field(default_factory=list)
    flight_attribute_filters: list[str] = Field(default_factory=list)
    airline_filters: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_search_constraints(self) -> "SearchRequest":
        if self.origin_city == self.destination_city:
            raise ValueError("origin and destination must be different")
        if self.max_price is not None and self.max_price <= 0:
            raise ValueError("max_price must be positive")
        return self


class FlightResult(BaseModel):
    flight_no: str
    airline: str
    origin_city: str
    destination_city: str
    departure_time: time
    arrival_time: time
    is_direct: bool
    stop_info: str
    price: int
    deeplink_url: str
    fallback_search_url: str


class SearchResponse(BaseModel):
    lowest_price: int | None = None
    flights: list[FlightResult]
    history_id: int | None = None


class HistoryRecord(SearchRequest):
    id: int
    last_searched_at: datetime
    created_at: datetime
    updated_at: datetime


class SessionState(BaseModel):
    id: int = 1
    session_status: str
    last_successful_scrape_at: datetime | None = None
    updated_at: datetime


class MonitorTaskBase(BaseModel):
    origin_city: str
    destination_city: str
    departure_date: date
    target_price: int
    check_interval_minutes: int
    departure_time_filters: list[str] = Field(default_factory=list)
    flight_attribute_filters: list[str] = Field(default_factory=list)
    airline_filters: list[str] = Field(default_factory=list)
    reminder_policy: Literal["no_repeat", "interval", "every_check"] = "interval"
    unchanged_reminder_interval_minutes: int = 360
    alert_sound_enabled: bool = True
    alert_taskbar_enabled: bool = True
    alert_popup_enabled: bool = True

    @model_validator(mode="after")
    def validate_monitor_constraints(self) -> "MonitorTaskBase":
        if self.origin_city == self.destination_city:
            raise ValueError("origin and destination must be different")
        if self.target_price <= 0:
            raise ValueError("target_price must be positive")
        if self.check_interval_minutes <= 0:
            raise ValueError("check_interval_minutes must be positive")
        if self.unchanged_reminder_interval_minutes <= 0:
            raise ValueError("unchanged_reminder_interval_minutes must be positive")
        return self


class MonitorTaskCreate(MonitorTaskBase):
    pass


class MonitorTaskUpdate(MonitorTaskBase):
    enabled: bool | None = None


class MonitorTask(MonitorTaskBase):
    id: int
    enabled: bool
    last_checked_at: datetime | None = None
    next_check_at: datetime
    last_seen_lowest_price: int | None = None
    last_notified_at: datetime | None = None
    last_notified_price: int | None = None
    created_at: datetime
    updated_at: datetime


class MonitorHit(BaseModel):
    id: int
    monitor_task_id: int
    hit_price: int
    hit_at: datetime
    search_snapshot_json: list[dict]
    lowest_price: int
    created_at: datetime


class MonitorCheckResult(BaseModel):
    id: int
    monitor_task_id: int
    checked_at: datetime
    status: Literal["success", "error", "session_expired"]
    lowest_price: int | None = None
    is_target_hit: bool
    notification_sent: bool
    error_message: str | None = None
    search_snapshot_json: list[dict]
    created_at: datetime
