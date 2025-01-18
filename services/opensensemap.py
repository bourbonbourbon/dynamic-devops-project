# pylint: disable=missing-module-docstring
# pylint: disable=missing-function-docstring
# pylint: disable=missing-class-docstring
import requests
import pandas


class OpenSenseMap:
    def __init__(self, base_url, headers=None):
        self.base_url = base_url
        self.headers = headers

    def get_all_temperatures(self, method="GET", params=None, data=None):
        url = f"{self.base_url}/boxes?date={params}&phenomenon=temperature&format=json"
        try:
            response = requests.request(
                method, url, headers=self.headers, params=params, data=data, timeout=15
            )
        except requests.exceptions.Timeout:
            return "Query timed out."

        if response.status_code == 200:

            temperature_info = []

            data = response.json()

            for entry in data:
                sensors = entry.get("sensors", [])

                for sensor in sensors:
                    if sensor.get("icon") == "osem-thermometer":

                        if (
                            sensor.get("lastMeasurement", "") != ""
                            and sensor.get("unit", "") == "°C"
                        ):
                            measurement_date = pandas.to_datetime(
                                sensor.get("lastMeasurement", {}).get("createdAt", ""),
                                utc=True,
                            )
                            current_date = pandas.to_datetime(params, utc=True)

                            date_diff_in_hours = (
                                measurement_date - current_date
                            ).total_seconds() // 3600

                            temperature_value = sensor.get("lastMeasurement", {}).get(
                                "value", ""
                            )

                            if (
                                measurement_date != ""
                                and date_diff_in_hours < 24
                                and temperature_value != ""
                            ):
                                temperature_info.append(float(temperature_value))

            return str((sum(temperature_info) / len(temperature_info)))

        else:
            return f"Error: {response.status_code}, {response.text}"
