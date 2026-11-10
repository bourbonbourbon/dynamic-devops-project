# pylint: disable=missing-module-docstring
# pylint: disable=missing-function-docstring
# pylint: disable=missing-class-docstring
from datetime import datetime, timedelta, timezone
from http import HTTPStatus

import requests

MAX_MEASUREMENT_AGE = timedelta(hours=1)


class OpenSenseMap:
    def __init__(self, base_url):
        self.base_url = base_url
        self.fail_count = 0

    def get_avg_temperature(self, sense_boxes=None):
        temperature_info = []

        for sense_box in sense_boxes:
            url = f"{self.base_url}/boxes/{sense_box}?format=json"
            try:
                response = requests.request(method="GET", url=url, timeout=60)
            except Exception:
                self.fail_count += 1
                continue

            if response.status_code == HTTPStatus.OK:
                temperature = self._process_temperature_data(data=response.json())
                if temperature is not None:
                    temperature_info.append(temperature)
                else:
                    self.fail_count += 1
            else:
                self.fail_count += 1

        if temperature_info:
            avg_temp = sum(temperature_info) / len(temperature_info)
            status = ""
            if avg_temp <= 10:
                status = "Too Cold"
            elif 10 < avg_temp <= 36:
                status = "Good"
            else:
                status = "Too Hot"
            return (
                ({"avg_temp": round(number=avg_temp, ndigits=2), "status": status}),
                HTTPStatus.OK,
                self.fail_count,
            )

        return (
            ({"avg_temp": 0, "status": "Internal Error"}),
            HTTPStatus.INTERNAL_SERVER_ERROR,
            self.fail_count,
        )

    def _process_temperature_data(self, data, now=None):
        if now is None:
            now = datetime.now(timezone.utc)

        for sensor in data.get("sensors", []):
            if sensor.get("icon") != "osem-thermometer":
                continue
            if sensor.get("unit") != "°C":
                continue

            last_measurement = sensor.get("lastMeasurement") or {}
            value = last_measurement.get("value")
            created_at = last_measurement.get("createdAt")
            if value in (None, "") or not created_at:
                continue

            measured_at = self._parse_timestamp(created_at)
            if measured_at is None:
                continue

            if now - measured_at <= MAX_MEASUREMENT_AGE:
                return float(value)

        return None

    @staticmethod
    def _parse_timestamp(text):
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
