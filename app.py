# pylint: disable=missing-module-docstring
# pylint: disable=missing-function-docstring
import datetime
from prometheus_client import Counter, generate_latest
from flask import Flask, jsonify
from version import __version__
from services.opensensemap import OpenSenseMap

total_version_requests = Counter("version_requests", "Total Number of version requests")
total_temp_requests = Counter("temp_requests", "Total Number of temperature requests")

app = Flask(__name__)

@app.route("/metrics")
def metrics():
    return generate_latest()

@app.route("/version")
def print_version():
    total_version_requests.inc()
    return jsonify({"version": __version__}), 200


@app.route("/temperature")
def temperature():
    date = (
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
    api = OpenSenseMap(base_url="https://api.opensensemap.org")
    data, return_code = api.get_avg_temperature(params=date)
    total_temp_requests.inc()
    return jsonify(data), return_code


if __name__ == "__main__":
    from waitress import serve

    serve(app, host="0.0.0.0", port="8080")
