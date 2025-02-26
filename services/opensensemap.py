# pylint: disable=missing-module-docstring
# pylint: disable=missing-function-docstring
# pylint: disable=missing-class-docstring
import datetime
import requests


class OpenSenseMap:
    def __init__(self, base_url, headers=None):
        self.base_url = base_url
        self.headers = headers

    def get_avg_temperature(self, method="GET", params=None, data=None):
        url = f"{self.base_url}/boxes?date={params}&phenomenon=temperature&format=json"
        response = requests.request(
            method, url, headers=self.headers, params=params, data=data, timeout=120
        )

        if response.status_code == 200:
            return self._process_temperature_data(response.json(), params), 200

        return {"err_msg": f"Error: {response.status_code}, {response.text}"}, 503

    def _process_temperature_data(self, data, date):
        temperature_info = []

        for entry in data:
            sensors = entry.get("sensors", [])
            temperature_info.extend(self._get_sensor_temperatures(sensors, date))

        if temperature_info:
            avg_temp = sum(temperature_info) / len(temperature_info)
            status = ""
            if avg_temp < 10:
                status = "Too Cold"
            elif 11 <= avg_temp <= 36:
                status = "Good"
            else:
                status = "Too Hot"
            return {"avg_temp": avg_temp, "status": status}
        return {"avg_temp": 0, "status": "Internal Error"}

    def _get_sensor_temperatures(self, sensors, date):
        temperatures = []
        current_date = datetime.datetime.fromisoformat(date)
        print(current_date, type(current_date))

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
                        temperatures.append(float(temperature_value))

        return temperatures
