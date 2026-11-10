# pylint: disable=missing-module-docstring
# pylint: disable=missing-function-docstring
import json
import logging
import os
from http import HTTPStatus
from pathlib import Path
from threading import Thread

import boto3
import valkey
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError
from dotenv import dotenv_values
from flask import Flask, jsonify
from prometheus_client import Counter, generate_latest

from services.opensensemap import OpenSenseMap
from version import __version__

logger = logging.getLogger(__name__)

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

# Environment variables take precedence over the .env file.
# Kubernetes and CI pass their values as environment variables.
config = {
    **dotenv_values(dotenv_path=Path(__file__).resolve().parent.parent / ".env"),
    **os.environ,
}

senseBoxes = config["SENSEBOXES"].split(sep=",")

app = Flask(import_name=__name__)

bucket_name = config["S3_BUCKET"]
object_name = config["S3_OBJECT"]

s3_client = boto3.client(
    service_name="s3",
    endpoint_url=config["S3_ENDPOINT_URL"],
    aws_access_key_id=config["S3_ACCESS_KEY"],
    aws_secret_access_key=config["S3_SECRET_KEY"],
    region_name=config.get("S3_REGION", "us-east-1"),
    config=Config(
        s3={"addressing_style": "path"},
        connect_timeout=5,
        read_timeout=10,
        retries={"max_attempts": 3},
    ),
)

valkey_client = valkey.Valkey(host=config["VKURL"], port=int(config["VKPORT"]), db=0)

SENSEBOX_FAIL_COUNT = 0


def ensure_bucket():
    try:
        s3_client.head_bucket(Bucket=bucket_name)
    except ClientError:
        s3_client.create_bucket(Bucket=bucket_name)
        print("created using bucket", bucket_name)


def _try_ensure_bucket():
    # Runs in a background thread, so the web server starts
    # even when RustFS is not reachable yet.
    try:
        ensure_bucket()
    except (BotoCoreError, ClientError) as err:
        logger.warning("Object storage is not ready: %s", err)


@app.route(rule="/metrics")
def metrics():
    return generate_latest()


@app.route(rule="/version")
def print_version():
    total_version_requests.inc()
    return jsonify({"version": __version__}), 200


def query_main_and_store():
    api = OpenSenseMap(base_url=BASE_URL)
    data, return_code, fail_count = api.get_avg_temperature(sense_boxes=senseBoxes)
    global SENSEBOX_FAIL_COUNT  # pylint: disable=global-statement
    SENSEBOX_FAIL_COUNT = fail_count

    payload = json.dumps(obj=data)
    try:
        s3_client.put_object(
            Bucket=bucket_name,
            Key=object_name,
            Body=payload.encode(encoding="UTF-8"),
            ContentType="application/json",
        )
    except (BotoCoreError, ClientError) as err:
        logger.error("Could not write to object storage: %s", err)

    if return_code == HTTPStatus.OK:
        valkey_client.set(name="avg-temp", value=payload, ex=300)
    return jsonify(data), return_code


@app.route(rule="/temperature")
def temperature():
    total_temp_requests.inc()
    cached = valkey_client.get(name="avg-temp")
    if cached is not None:
        try:
            v_value = json.loads(s=cached.decode(encoding="UTF-8"))
        except json.JSONDecodeError:
            # Old cache entries use the Python text format. Treat them as a miss.
            v_value = None

        if v_value is not None:
            if v_value.get("status") == "Internal Error":
                return jsonify(v_value), HTTPStatus.INTERNAL_SERVER_ERROR
            return jsonify(v_value), HTTPStatus.OK

    return query_main_and_store()


@app.route(rule="/store")
def store():
    query_main_and_store()
    total_store_requests.inc()
    return temperature()


@app.route(rule="/readyz")
def readyz():
    most_sense_boxes_working = SENSEBOX_FAIL_COUNT < (len(senseBoxes) // 2) + 1
    v_value = valkey_client.get(name="avg-temp")
    v_ttl = valkey_client.ttl(name="avg-temp")

    if most_sense_boxes_working and v_value is not None and v_ttl > 1:
        return str(SENSEBOX_FAIL_COUNT), HTTPStatus.OK
    return str(SENSEBOX_FAIL_COUNT), HTTPStatus.INTERNAL_SERVER_ERROR


if __name__ == "__main__":
    from waitress import serve

    logging.basicConfig(level=logging.INFO)
    Thread(target=_try_ensure_bucket, daemon=True).start()
    serve(app=app, host=config["HOST"], port=int(config["PORT"]))
