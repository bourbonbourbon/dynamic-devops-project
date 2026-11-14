# pylint: disable=missing-module-docstring
# pylint: disable=missing-function-docstring
# pylint: disable=redefined-outer-name
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError
from prometheus_client import REGISTRY
from valkey.exceptions import ValkeyError

import app as app_module
from app import (
    app,
    bucket_name,
    ensure_bucket,
    object_name,
    refresh_cache,
    valkey_client,
)
from services.opensensemap import OpenSenseMap
from version import __version__


@pytest.fixture
def client():
    with app.test_client() as client_var:
        yield client_var


@pytest.fixture(autouse=True)
def clear_cache():
    # Remove cached values so that each test starts from the same state.
    valkey_client.flushdb()
    yield


def test_version_success(client):
    response = client.get("/version")
    assert response.status_code == HTTPStatus.OK
    assert response.json == {"version": __version__}


@patch("app.OpenSenseMap")
@patch("app.s3_client")
def test_store_writes_to_rustfs(mock_s3, mock_api_class, client):
    mock_api_class.return_value.get_avg_temperature.return_value = (
        {"avg_temp": 6.77, "status": "Too Cold"},
        HTTPStatus.OK,
        0,
    )

    response = client.get("/store")

    assert response.status_code == HTTPStatus.OK
    mock_s3.put_object.assert_called_once()
    kwargs = mock_s3.put_object.call_args.kwargs
    assert kwargs["Bucket"] == bucket_name
    assert kwargs["Key"] == object_name


@patch("app.s3_client")
def test_ensure_bucket_creates_missing_bucket(mock_s3):
    not_found = ClientError(
        {"Error": {"Code": "404", "Message": "Not Found"}}, "HeadBucket"
    )
    mock_s3.head_bucket.side_effect = not_found

    ensure_bucket()

    mock_s3.create_bucket.assert_called_once_with(Bucket=bucket_name)


@patch("app.s3_client")
def test_ensure_bucket_skips_existing_bucket(mock_s3):
    ensure_bucket()

    mock_s3.head_bucket.assert_called_once_with(Bucket=bucket_name)
    mock_s3.create_bucket.assert_not_called()


@patch("requests.request")
def test_box_without_thermometer_is_counted_as_failed(mock_request):
    mock_request.return_value.status_code = HTTPStatus.OK
    mock_request.return_value.json.return_value = {"sensors": []}

    api = OpenSenseMap(base_url="https://example.test")
    data, status, fail_count = api.get_avg_temperature(sense_boxes=["box1"])

    assert status == HTTPStatus.INTERNAL_SERVER_ERROR
    assert data == {"avg_temp": 0, "status": "Internal Error"}
    assert fail_count == 1


def test_temperature_reads_json_cache(client):
    valkey_client.set(
        name="avg-temp",
        value=json.dumps(obj={"avg_temp": 12.5, "status": "Good"}),
        ex=300,
    )

    response = client.get("/temperature")

    assert response.status_code == HTTPStatus.OK
    assert response.json == {"avg_temp": 12.5, "status": "Good"}


def fresh_box_payload(value=6.77, age=timedelta(minutes=10)):
    created = (datetime.now(timezone.utc) - age).isoformat()
    return {
        "sensors": [
            {
                "icon": "osem-thermometer",
                "unit": "°C",
                "lastMeasurement": {"value": str(value), "createdAt": created},
            }
        ]
    }


def test_measurement_older_than_one_hour_is_rejected():
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    data = fresh_box_payload(age=timedelta(minutes=0))
    data["sensors"][0]["lastMeasurement"]["createdAt"] = "2026-01-01T10:30:00.000Z"

    api = OpenSenseMap(base_url="https://example.test")

    result = api._process_temperature_data(
        data, now=now
    )  # pylint: disable=protected-access
    assert result is None


def test_measurement_within_one_hour_is_accepted():
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    data = fresh_box_payload(value=20.5, age=timedelta(minutes=0))
    data["sensors"][0]["lastMeasurement"]["createdAt"] = "2026-01-01T11:30:00.000Z"

    api = OpenSenseMap(base_url="https://example.test")

    result = api._process_temperature_data(
        data, now=now
    )  # pylint: disable=protected-access
    assert result == 20.5


@patch("app.s3_client")
@patch("requests.request")
def test_temperature_success(mock_request, mock_s3, client):
    mock_request.return_value.status_code = HTTPStatus.OK
    mock_request.return_value.json.return_value = fresh_box_payload(value=6.77)

    response = client.get("/temperature")

    assert response.status_code == HTTPStatus.OK
    assert response.json == {"avg_temp": 6.77, "status": "Too Cold"}
    mock_s3.put_object.assert_called_once()


@patch("app.s3_client")
@patch("app.OpenSenseMap")
def test_internal_error_is_not_cached(mock_api_class, mock_s3, client):
    mock_api_class.return_value.get_avg_temperature.return_value = (
        {"avg_temp": 0, "status": "Internal Error"},
        HTTPStatus.INTERNAL_SERVER_ERROR,
        1,
    )

    response = client.get("/temperature")

    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert valkey_client.get(name="avg-temp") is None
    mock_s3.put_object.assert_called_once()


@patch("app.OpenSenseMap")
@patch("app.s3_client")
def test_store_returns_503_when_storage_is_down(mock_s3, mock_api_class, client):
    mock_api_class.return_value.get_avg_temperature.return_value = (
        {"avg_temp": 6.77, "status": "Too Cold"},
        HTTPStatus.OK,
        0,
    )
    mock_s3.put_object.side_effect = ClientError(
        {"Error": {"Code": "500", "Message": "down"}}, "PutObject"
    )

    response = client.get("/store")

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.json == {"error": "object storage unavailable"}
    assert valkey_client.get(name="avg-temp") is None


@patch("app.OpenSenseMap")
@patch("app.s3_client")
def test_refresh_cache_runs_without_request_context(mock_s3, mock_api_class):
    mock_api_class.return_value.get_avg_temperature.return_value = (
        {"avg_temp": 6.77, "status": "Too Cold"},
        HTTPStatus.OK,
        0,
    )

    data, return_code = refresh_cache()

    assert return_code == HTTPStatus.OK
    assert data == {"avg_temp": 6.77, "status": "Too Cold"}
    assert valkey_client.get(name="avg-temp") is not None
    mock_s3.put_object.assert_called_once()


def metric_value(name):
    return REGISTRY.get_sample_value(name)


@patch("app.s3_client")
@patch("app.OpenSenseMap")
def test_successful_refresh_sets_timestamps(mock_api_class, mock_s3):
    mock_api_class.return_value.get_avg_temperature.return_value = (
        {"avg_temp": 6.77, "status": "Too Cold"},
        HTTPStatus.OK,
        0,
    )

    before = time.time()
    refresh_cache()
    after = time.time()

    assert before <= metric_value("cache_last_refresh_timestamp_seconds") <= after
    assert before <= metric_value("store_last_write_timestamp_seconds") <= after
    mock_s3.put_object.assert_called_once()


@patch("app.s3_client")
@patch("app.OpenSenseMap")
def test_failed_store_does_not_update_store_timestamp(mock_api_class, mock_s3):
    mock_api_class.return_value.get_avg_temperature.return_value = (
        {"avg_temp": 6.77, "status": "Too Cold"},
        HTTPStatus.OK,
        0,
    )
    mock_s3.put_object.side_effect = ClientError(
        {"Error": {"Code": "500", "Message": "down"}}, "PutObject"
    )
    before_store = metric_value("store_last_write_timestamp_seconds")

    refresh_cache()

    assert metric_value("store_last_write_timestamp_seconds") == before_store


@patch("app.s3_client")
@patch("app.OpenSenseMap")
def test_internal_error_does_not_update_cache_timestamp(mock_api_class, mock_s3):
    mock_api_class.return_value.get_avg_temperature.return_value = (
        {"avg_temp": 0, "status": "Internal Error"},
        HTTPStatus.INTERNAL_SERVER_ERROR,
        1,
    )
    before_cache = metric_value("cache_last_refresh_timestamp_seconds")

    refresh_cache()

    assert metric_value("cache_last_refresh_timestamp_seconds") == before_cache
    assert metric_value("failed_sensebox_count") == 1
    mock_s3.put_object.assert_called_once()


def test_metrics_endpoint_exports_new_metrics(client):
    response = client.get("/metrics")

    assert response.status_code == HTTPStatus.OK
    assert response.mimetype == "text/plain"
    assert b"cache_last_refresh_timestamp_seconds" in response.data
    assert b"store_last_write_timestamp_seconds" in response.data
    assert b"failed_sensebox_count" in response.data


@patch("requests.request")
def test_failed_senseboxes_are_logged_by_id(mock_request, caplog):
    mock_request.return_value.status_code = HTTPStatus.NOT_FOUND

    api = OpenSenseMap(base_url="https://example.test")
    with caplog.at_level(logging.WARNING):
        api.get_avg_temperature(sense_boxes=["box-abc"])

    assert "senseBox box-abc failed: HTTP status 404" in caplog.text


@patch("requests.request")
def test_box_without_reading_is_logged_by_id(mock_request, caplog):
    mock_request.return_value.status_code = HTTPStatus.OK
    mock_request.return_value.json.return_value = {"sensors": []}

    api = OpenSenseMap(base_url="https://example.test")
    with caplog.at_level(logging.WARNING):
        api.get_avg_temperature(sense_boxes=["box-xyz"])

    assert "senseBox box-xyz failed: no usable temperature reading" in caplog.text


@pytest.mark.parametrize(
    "value, expected_status",
    [
        (10.0, "Too Cold"),
        (10.004, "Too Cold"),
        (10.006, "Good"),
        (36.0, "Good"),
        (36.01, "Too Hot"),
    ],
)
@patch("requests.request")
def test_status_thresholds(mock_request, value, expected_status):
    mock_request.return_value.status_code = HTTPStatus.OK
    mock_request.return_value.json.return_value = fresh_box_payload(value=value)

    api = OpenSenseMap(base_url="https://example.test")
    data, status, _ = api.get_avg_temperature(sense_boxes=["box1"])

    assert status == HTTPStatus.OK
    assert data["status"] == expected_status


@patch("app.valkey_client")
def test_temperature_returns_503_when_cache_is_down(mock_valkey, client):
    mock_valkey.get.side_effect = ValkeyError("cache down")

    response = client.get("/temperature")

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.json == {"error": "cache unavailable"}


@patch("app.valkey_client")
def test_readyz_returns_503_when_cache_is_down(mock_valkey, client):
    mock_valkey.ping.side_effect = ValkeyError("cache down")

    response = client.get("/readyz")

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.json == {"error": "cache unavailable"}


@pytest.fixture
def ready_app(monkeypatch):
    """Set the app to a healthy state with a mocked Valkey client."""
    now = time.time()
    monkeypatch.setattr(app_module, "valkey_client", MagicMock())
    monkeypatch.setattr(app_module, "LAST_CACHE_REFRESH", now)
    monkeypatch.setattr(app_module, "LAST_STORE_WRITE", now)
    monkeypatch.setattr(app_module, "SENSEBOX_FAIL_COUNT", 0)
    return monkeypatch


def test_readyz_ready_when_all_checks_pass(client, ready_app):
    response = client.get("/readyz")

    assert response.status_code == HTTPStatus.OK
    assert response.json["ready"] is True


def test_readyz_ready_at_sensebox_threshold(client, ready_app):
    total = len(app_module.senseBoxes)
    ready_app.setattr(app_module, "SENSEBOX_FAIL_COUNT", total - (total // 2 + 1))

    response = client.get("/readyz")

    assert response.status_code == HTTPStatus.OK


def test_readyz_not_ready_when_too_many_senseboxes_fail(client, ready_app):
    total = len(app_module.senseBoxes)
    ready_app.setattr(app_module, "SENSEBOX_FAIL_COUNT", total - (total // 2))

    response = client.get("/readyz")

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.json["checks"]["senseboxes_reachable"] is False


def test_readyz_not_ready_when_cache_is_too_old(client, ready_app):
    too_old = time.time() - 2 * app_module.CYCLE_SECONDS - 1
    ready_app.setattr(app_module, "LAST_CACHE_REFRESH", too_old)

    response = client.get("/readyz")

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.json["checks"]["cache_fresh"] is False


def test_readyz_not_ready_when_store_is_too_old(client, ready_app):
    too_old = time.time() - 2 * app_module.CYCLE_SECONDS - 1
    ready_app.setattr(app_module, "LAST_STORE_WRITE", too_old)

    response = client.get("/readyz")

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.json["checks"]["store_fresh"] is False


def test_readyz_not_ready_before_first_refresh(client, ready_app):
    ready_app.setattr(app_module, "LAST_CACHE_REFRESH", 0.0)
    ready_app.setattr(app_module, "LAST_STORE_WRITE", 0.0)

    response = client.get("/readyz")

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.json["ready"] is False


@pytest.mark.parametrize(
    "age, expected",
    [
        (timedelta(hours=1), 20.5),
        (timedelta(hours=1, seconds=1), None),
    ],
)
def test_measurement_age_boundary(age, expected):
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    data = fresh_box_payload(value=20.5)
    data["sensors"][0]["lastMeasurement"]["createdAt"] = (now - age).isoformat()

    api = OpenSenseMap(base_url="https://example.test")

    result = api._process_temperature_data(
        data, now=now
    )  # pylint: disable=protected-access
    assert result == expected


@pytest.mark.parametrize(
    "extra_seconds, expected_status",
    [
        (0, HTTPStatus.OK),
        (1, HTTPStatus.SERVICE_UNAVAILABLE),
    ],
)
def test_readyz_cache_age_boundary(client, ready_app, extra_seconds, expected_status):
    fixed_now = 10_000.0
    max_age = 2 * app_module.CYCLE_SECONDS
    ready_app.setattr(app_module, "time", SimpleNamespace(time=lambda: fixed_now))
    ready_app.setattr(
        app_module, "LAST_CACHE_REFRESH", fixed_now - max_age - extra_seconds
    )
    ready_app.setattr(app_module, "LAST_STORE_WRITE", fixed_now)

    response = client.get("/readyz")

    assert response.status_code == expected_status
