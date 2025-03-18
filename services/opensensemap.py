# pylint: disable=missing-module-docstring
# pylint: disable=missing-function-docstring
# pylint: disable=missing-class-docstring
import datetime
from http import HTTPStatus
import requests


class OpenSenseMap:
    def __init__(self, base_url):
        self.base_url = base_url

    def get_avg_temperature(self, sense_boxes=None):
        temperature_info = []

        for sense_box in sense_boxes:
            url = f"{self.base_url}/boxes/{sense_box}?format=json"
            try:
                response = requests.request("GET", url, timeout=60)
            except Exception:
                return (
                    ({"avg_temp": 0, "status": "Internal Error"}),
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                )

            if response.status_code == HTTPStatus.OK:
                temperature_info.append(self._process_temperature_data(response.json()))
            else:
                pass  # check stage increment a failure counter

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
                ({"avg_temp": round(avg_temp, 2), "status": status}),
                HTTPStatus.OK,
            )

        return (
            ({"avg_temp": 0, "status": "Internal Error"}),
            HTTPStatus.INTERNAL_SERVER_ERROR,
        )

    def _process_temperature_data(self, data):
        sensors = data.get("sensors", [])

        current_date = datetime.datetime.fromisoformat(
            datetime.datetime.now()
            .replace(
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )
            .isoformat()
            + "Z"
        )

        for sensor in sensors:
            if sensor.get("icon") == "osem-thermometer":
                last_measurement = sensor.get("lastMeasurement", {})
                if last_measurement and sensor.get("unit") == "°C":
                    measurement_date = datetime.datetime.fromisoformat(
                        last_measurement.get("createdAt", "")
                    )
                    date_diff_in_hours = (
                        measurement_date - current_date
                    ).total_seconds() // 3600
                    temperature_value = last_measurement.get("value", "")

                    if date_diff_in_hours < 24 and temperature_value != "":
                        return float(temperature_value)

        return None  # handle none
