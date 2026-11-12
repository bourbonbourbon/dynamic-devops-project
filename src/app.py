# pylint: disable=missing-module-docstring
# pylint: disable=missing-function-docstring
import json
import logging
import os
import time
from http import HTTPStatus
from pathlib import Path
from threading import Thread

import boto3
import valkey
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError
from dotenv import dotenv_values
from flask import Flask, jsonify
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, generate_latest
from valkey.exceptions import ValkeyError

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

last_cache_refresh = Gauge(
    name="cache_last_refresh_timestamp_seconds",
    documentation="Unix time of the last successful cache refresh",
)
last_store_write = Gauge(
    name="store_last_write_timestamp_seconds",
    documentation="Unix time of the last successful write to object storage",
)
failed_sensebox_count = Gauge(
    name="failed_sensebox_count",
    documentation="Number of senseBoxes that failed in the last refresh",
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

CYCLE_SECONDS = 300  # Refresh interval and cache lifetime
LAST_CACHE_REFRESH = 0.0  # Unix time of the last successful cache write
LAST_STORE_WRITE = 0.0  # Unix time of the last successful RustFS write


class StorageWriteError(Exception):
    """Raised when a required write to object storage fails."""


@app.errorhandler(ValkeyError)
def cache_unavailable(err):
    logger.error("Cache unavailable: %s", err)
    return jsonify({"error": "cache unavailable"}), HTTPStatus.SERVICE_UNAVAILABLE


def ensure_bucket():
    try:
        s3_client.head_bucket(Bucket=bucket_name)
    except ClientError:
        s3_client.create_bucket(Bucket=bucket_name)
        logger.info("Created bucket %s", bucket_name)


def _try_ensure_bucket():
    # Runs in a background thread, so the web server starts
    # even when RustFS is not reachable yet.
    try:
        ensure_bucket()
    except (BotoCoreError, ClientError) as err:
        logger.warning("Object storage is not ready: %s", err)


@app.route(rule="/metrics")
def metrics():
    return (
        generate_latest(),
        HTTPStatus.OK,
        {"Content-Type": CONTENT_TYPE_LATEST},
    )


@app.route(rule="/version")
def print_version():
    total_version_requests.inc()
    return jsonify({"version": __version__}), 200


def refresh_cache(require_storage=False):
    """Fetch the temperatures, store them in RustFS, and cache them in Valkey.

    This function does not use Flask request objects, so the scheduler
    thread can call it.
    """
    global SENSEBOX_FAIL_COUNT, LAST_CACHE_REFRESH, LAST_STORE_WRITE  # pylint: disable=global-statement
    api = OpenSenseMap(base_url=BASE_URL)
    data, return_code, fail_count = api.get_avg_temperature(sense_boxes=senseBoxes)
    SENSEBOX_FAIL_COUNT = fail_count
    failed_sensebox_count.set(fail_count)

    payload = json.dumps(obj=data)
    try:
        s3_client.put_object(
            Bucket=bucket_name,
            Key=object_name,
            Body=payload.encode(encoding="UTF-8"),
            ContentType="application/json",
        )
        LAST_STORE_WRITE = time.time()
        last_store_write.set(LAST_STORE_WRITE)
    except (BotoCoreError, ClientError) as err:
        if require_storage:
            raise StorageWriteError(str(err)) from err
        logger.error("Could not write to object storage: %s", err)

    if return_code == HTTPStatus.OK:
        valkey_client.set(name="avg-temp", value=payload, ex=CYCLE_SECONDS)
        LAST_CACHE_REFRESH = time.time()
        last_cache_refresh.set(LAST_CACHE_REFRESH)
    return data, return_code


def query_main_and_store():
    data, return_code = refresh_cache()
    return jsonify(data), return_code


def run_scheduler():
    """Create the bucket, then refresh the cache and storage every cycle."""
    _try_ensure_bucket()
    while True:
        try:
            refresh_cache()
        except Exception:  # pylint: disable=broad-exception-caught
            # The loop must keep running after any failure.
            logger.exception("Scheduled refresh failed")
        time.sleep(CYCLE_SECONDS)


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
    total_store_requests.inc()
    try:
        data, return_code = refresh_cache(require_storage=True)
    except StorageWriteError as err:
        logger.error("Store failed: %s", err)
        return (
            jsonify({"error": "object storage unavailable"}),
            HTTPStatus.SERVICE_UNAVAILABLE,
        )
    return jsonify(data), return_code


@app.route(rule="/readyz")
def readyz():
    valkey_client.ping()  # Raises ValkeyError when the cache is down.

    now = time.time()
    max_age = 2 * CYCLE_SECONDS
    total = len(senseBoxes)
    reachable = total - SENSEBOX_FAIL_COUNT

    checks = {
        "senseboxes_reachable": reachable >= total // 2 + 1,
        "cache_fresh": LAST_CACHE_REFRESH > 0 and now - LAST_CACHE_REFRESH <= max_age,
        "store_fresh": LAST_STORE_WRITE > 0 and now - LAST_STORE_WRITE <= max_age,
    }
    ready = all(checks.values())
    status = HTTPStatus.OK if ready else HTTPStatus.SERVICE_UNAVAILABLE
    return (
        jsonify({"ready": ready, "checks": checks, "reachable_senseboxes": reachable}),
        status,
    )


if __name__ == "__main__":
    from waitress import serve

    logging.basicConfig(level=logging.INFO)
    Thread(target=run_scheduler, daemon=True).start()
    serve(app=app, host=config["HOST"], port=int(config["PORT"]))
