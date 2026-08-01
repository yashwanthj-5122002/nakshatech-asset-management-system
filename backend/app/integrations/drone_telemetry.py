"""Extension point for real drone telemetry integrations.

Connect a manufacturer SDK, remote-controller application, GPS tracker, or
telemetry gateway and transform its payload into DroneLocationCreate.
"""

from abc import ABC, abstractmethod

from app.schemas.drone import DroneLocationCreate


class DroneTelemetryAdapter(ABC):
    @abstractmethod
    def parse(self, payload: dict) -> DroneLocationCreate:
        raise NotImplementedError


class GenericJsonTelemetryAdapter(DroneTelemetryAdapter):
    def parse(self, payload: dict) -> DroneLocationCreate:
        return DroneLocationCreate(
            latitude=payload["latitude"],
            longitude=payload["longitude"],
            altitude=payload.get("altitude"),
            speed=payload.get("speed"),
            heading=payload.get("heading"),
            battery_percent=payload.get("battery_percent"),
            source=payload.get("source", "generic-json"),
        )
