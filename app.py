# pylint: disable=missing-module-docstring
# pylint: disable=missing-function-docstring
import datetime
from flask import Flask, jsonify
from version import __version__
from services.opensensemap import OpenSenseMap

app = Flask(__name__)


@app.route("/version")
def print_version():
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
    data, return_code = api.get_all_temperatures(params=date)
    return jsonify(data), return_code


if __name__ == "__main__":
    app.run(host="0.0.0.0", port="5000")
