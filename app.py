# pylint: disable=missing-module-docstring
# pylint: disable=missing-function-docstring
# import datetime
import io
import json
import ast
import datetime
from http import HTTPStatus
import minio
import valkey
from prometheus_client import Counter, generate_latest
from dotenv import dotenv_values
from flask import Flask, jsonify
from version import __version__
from services.opensensemap import OpenSenseMap

total_version_requests = Counter(
    name="version_requests", documentation="Total Number of version requests"
)
total_temp_requests = Counter(
    name="temp_requests", documentation="Total Number of temperature requests"
)
total_store_requests = Counter(
    name="store_requests", documentation="Total Number of store requests"
)


BASE_URL = "https://api.opensensemap.org"

config = dotenv_values(dotenv_path=".env")

senseBoxes = config["SENSEBOXES"].split(sep=",")

app = Flask(import_name=__name__)

bucket_name = config["MBUCKET"]
object_name = config["MOBJECT"]
minio_client = minio.Minio(
    endpoint=config["MURL"],
    access_key=config["MAK"],
    secret_key=config["MSK"],
    secure=False,
)

valkey_client = valkey.Valkey(host=config["VKURL"], port=config["VKPORT"], db=0)


@app.route(rule="/metrics")
def metrics():
    return generate_latest()


@app.route(rule="/version")
def print_version():
    total_version_requests.inc()
    return jsonify({"version": __version__}), 200


@app.route(rule="/temperature")
def temperature():
    v_value = valkey_client.get(name="avg-temp")
    if v_value is not None:
        v_value = json.loads(
            s=json.dumps(
                obj=ast.literal_eval(node_or_string=v_value.decode(encoding="UTF-8"))
            )
        )
        if v_value.get("status") == "Internal Error":
            return jsonify(v_value), HTTPStatus.INTERNAL_SERVER_ERROR
        else:
            return jsonify(v_value), HTTPStatus.OK
    api = OpenSenseMap(base_url=BASE_URL)
    data, return_code = api.get_avg_temperature(sense_boxes=senseBoxes)

    data_as_bytes = str(object=data).encode(encoding="UTF-8")
    data_to_minio_stream = io.BytesIO(initial_bytes=data_as_bytes)
    minio_client.put_object(
        bucket_name=bucket_name,
        object_name=object_name,
        data=data_to_minio_stream,
        length=len(data_as_bytes),
    )

    valkey_client.set(name="avg-temp", value=str(object=data), ex=3000)

    total_temp_requests.inc()
    return jsonify(data), return_code


@app.route(rule="/store")
def store():
    total_store_requests.inc()
    return temperature()


@app.route(rule="/readyz")
def readyz():
    # prometheus
    pass


if __name__ == "__main__":
    bucket_found = minio_client.bucket_exists(bucket_name=bucket_name)
    if not bucket_found:
        minio_client.make_bucket(bucket_name=bucket_name)

    from waitress import serve

    serve(app=app, host=config["HOST"], port=config["PORT"])
