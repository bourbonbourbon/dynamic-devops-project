# pylint: disable=missing-module-docstring
# pylint: disable=missing-function-docstring
# pylint: disable=redefined-outer-name
import contextlib
import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from types import SimpleNamespace
from unittest.mock import patch

import boto3
import pytest
import valkey
from botocore.client import Config
from botocore.exceptions import ClientError

import app as app_module

pytestmark = pytest.mark.integration

GOOD_RESULT = {"avg_temp": 20.0, "status": "Good"}


def sensebox_payload(value, age=timedelta(minutes=10)):
    measured_at = datetime.now(timezone.utc) - age
    thermometer = {
        "icon": "osem-thermometer",
        "unit": "°C",
        "lastMeasurement": {
            "value": str(value),
            "createdAt": measured_at.isoformat(),
        },
    }
    return {"sensors": [thermometer]}


def api_response(status_code, payload=None):
    return SimpleNamespace(status_code=status_code, json=lambda: payload)


def cached_value():
    raw = app_module.valkey_client.get(name="avg-temp")
    return None if raw is None else json.loads(raw)


def read_stored_object():
    result = app_module.s3_client.get_object(
        Bucket=app_module.bucket_name, Key=app_module.object_name
    )
    return result["ContentType"], json.loads(result["Body"].read())


def stored_object_exists():
    try:
        app_module.s3_client.head_object(
            Bucket=app_module.bucket_name, Key=app_module.object_name
        )
    except ClientError as err:
        if err.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
            return False
        raise
    return True


@pytest.fixture
def sensebox_api():
    """Replace only the openSenseMap HTTP call. Valkey and RustFS stay real."""
    with patch("requests.request") as mock_request:
        mock_request.return_value = api_response(HTTPStatus.OK, sensebox_payload(20.0))
        yield mock_request


@pytest.fixture
def unreachable_storage(monkeypatch):
    broken = boto3.client(
        service_name="s3",
        endpoint_url="http://127.0.0.1:1",
        aws_access_key_id="unused",
        aws_secret_access_key="unused",
        region_name="us-east-1",
        config=Config(
            s3={"addressing_style": "path"},
            connect_timeout=1,
            read_timeout=1,
            retries={"max_attempts": 1},
        ),
    )
    monkeypatch.setattr(app_module, "s3_client", broken)


# --- Write paths ---


def test_store_writes_to_rustfs_and_valkey(client, sensebox_api):
    response = client.get("/store")

    assert response.status_code == HTTPStatus.OK
    assert response.json == GOOD_RESULT
    content_type, stored = read_stored_object()
    assert content_type == "application/json"
    assert stored == GOOD_RESULT
    assert cached_value() == GOOD_RESULT
    ttl = app_module.valkey_client.ttl(name="avg-temp")
    assert 0 < ttl <= app_module.CYCLE_SECONDS
    assert sensebox_api.call_count == len(app_module.senseBoxes)


def test_cache_writes_to_valkey_only(client, sensebox_api):
    response = client.get("/cache")

    assert response.status_code == HTTPStatus.OK
    assert cached_value() == GOOD_RESULT
    assert not stored_object_exists()
    assert sensebox_api.call_count == len(app_module.senseBoxes)


def test_refresh_cache_writes_both_services_without_a_request(sensebox_api):
    data, return_code = app_module.refresh_cache()

    assert return_code == HTTPStatus.OK
    assert data == GOOD_RESULT
    assert cached_value() == GOOD_RESULT
    assert read_stored_object()[1] == GOOD_RESULT
    assert sensebox_api.call_count == len(app_module.senseBoxes)


# --- /temperature ---


def test_temperature_miss_fills_both_services_and_hit_uses_the_cache(
    client, sensebox_api
):
    first = client.get("/temperature")
    calls_after_first = sensebox_api.call_count
    second = client.get("/temperature")

    assert first.status_code == HTTPStatus.OK
    assert first.json == GOOD_RESULT
    assert second.json == GOOD_RESULT
    assert calls_after_first == len(app_module.senseBoxes)
    assert sensebox_api.call_count == calls_after_first
    assert cached_value() == GOOD_RESULT
    assert read_stored_object()[1] == GOOD_RESULT


def test_temperature_fetches_again_when_the_cache_entry_has_expired(
    client, sensebox_api
):
    stale = {"avg_temp": 1.0, "status": "Too Cold"}
    app_module.valkey_client.set(name="avg-temp", value=json.dumps(stale), px=50)
    time.sleep(0.2)

    response = client.get("/temperature")

    assert response.json == GOOD_RESULT
    assert sensebox_api.call_count == len(app_module.senseBoxes)


def test_temperature_returns_500_and_caches_nothing_when_all_senseboxes_fail(
    client, sensebox_api
):
    sensebox_api.return_value = api_response(HTTPStatus.NOT_FOUND)

    response = client.get("/temperature")

    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert response.json == {"avg_temp": 0, "status": "Internal Error"}
    assert cached_value() is None
    assert app_module.SENSEBOX_FAIL_COUNT == len(app_module.senseBoxes)


def test_temperature_averages_only_the_working_senseboxes(client, sensebox_api):
    total = len(app_module.senseBoxes)
    failing = 2
    bad = api_response(HTTPStatus.NOT_FOUND)
    good = api_response(HTTPStatus.OK, sensebox_payload(20.0))
    sensebox_api.side_effect = [bad] * failing + [good] * (total - failing)

    response = client.get("/temperature")

    assert response.status_code == HTTPStatus.OK
    assert response.json == GOOD_RESULT
    assert app_module.SENSEBOX_FAIL_COUNT == failing


# --- /readyz ---


def test_readyz_follows_the_real_refresh_state(client, sensebox_api):
    before = client.get("/readyz")
    client.get("/store")
    after = client.get("/readyz")

    assert before.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert after.status_code == HTTPStatus.OK
    assert after.json["checks"] == {
        "senseboxes_reachable": True,
        "cache_fresh": True,
        "store_fresh": True,
    }


def test_readyz_is_not_ready_when_only_the_cache_was_updated(client, sensebox_api):
    client.get("/cache")

    response = client.get("/readyz")

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.json["checks"]["cache_fresh"] is True
    assert response.json["checks"]["store_fresh"] is False


# --- Bucket setup ---


def test_ensure_bucket_creates_a_missing_bucket_and_is_repeatable(monkeypatch):
    name = f"it-{uuid.uuid4().hex[:12]}"
    monkeypatch.setattr(app_module, "bucket_name", name)
    try:
        app_module.ensure_bucket()
        app_module.ensure_bucket()
        app_module.s3_client.head_bucket(Bucket=name)
    finally:
        with contextlib.suppress(ClientError):
            app_module.s3_client.delete_bucket(Bucket=name)


# --- Failure of one service ---


@pytest.mark.usefixtures("sensebox_api")
@pytest.mark.parametrize("path", ["/temperature", "/cache", "/store", "/readyz"])
def test_endpoints_return_503_when_valkey_is_unreachable(client, monkeypatch, path):
    unreachable = valkey.Valkey(host="127.0.0.1", port=1, socket_connect_timeout=1)
    monkeypatch.setattr(app_module, "valkey_client", unreachable)

    response = client.get(path)

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.json == {"error": "cache unavailable"}


@pytest.mark.usefixtures("unreachable_storage", "sensebox_api")
def test_store_returns_503_and_skips_the_cache_when_rustfs_is_unreachable(client):
    response = client.get("/store")

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.json == {"error": "object storage unavailable"}
    assert cached_value() is None


@pytest.mark.usefixtures("unreachable_storage", "sensebox_api")
def test_temperature_still_works_when_rustfs_is_unreachable(client):
    response = client.get("/temperature")

    assert response.status_code == HTTPStatus.OK
    assert response.json == GOOD_RESULT
    assert cached_value() == GOOD_RESULT
    assert app_module.LAST_STORE_WRITE == 0.0
