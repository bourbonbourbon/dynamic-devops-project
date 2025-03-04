# pylint: disable=missing-module-docstring
# pylint: disable=missing-function-docstring
# import datetime
from prometheus_client import Counter, generate_latest
from dotenv import dotenv_values
from flask import Flask, jsonify
from version import __version__
from services.opensensemap import OpenSenseMap

total_version_requests = Counter("version_requests", "Total Number of version requests")
total_temp_requests = Counter("temp_requests", "Total Number of temperature requests")

BASE_URL = "https://api.opensensemap.org"

config = dotenv_values(".env")

senseBoxes = config["SENSEBOXES"].split(",")

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
    api = OpenSenseMap(base_url=BASE_URL)
    data, return_code = api.get_avg_temperature(sense_boxes=senseBoxes)
    total_temp_requests.inc()
    return jsonify(data), return_code


if __name__ == "__main__":
    from waitress import serve

    serve(app, host=config["HOST"], port=config["PORT"])
