from datetime import datetime

from pydantic import BaseModel, Field


class DroneLocationCreate(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    altitude: float | None = None
    speed: float | None = Field(default=None, ge=0)
    heading: float | None = Field(default=None, ge=0, le=360)
    battery_percent: float | None = Field(default=None, ge=0, le=100)
    source: str = "manual"


class DroneLocationResponse(DroneLocationCreate):
    id: int
    drone_id: int
    recorded_at: datetime

    model_config = {"from_attributes": True}
