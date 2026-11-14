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
import requests
from botocore.exceptions import ClientError, EndpointConnectionError
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


OK_RESULT = ({"avg_temp": 6.77, "status": "Too Cold"}, HTTPStatus.OK, 0)


def make_response(status_code, payload=None):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload
    return response


FAILURES = [
    pytest.param(
        lambda *_args, **_kwargs: make_response(HTTPStatus.NOT_FOUND), id="http-404"
    ),
    pytest.param(requests.ConnectionError("no network"), id="connection-error"),
]


# --- /temperature: cache miss, stale data, failed senseBoxes ---


@patch("app.s3_client")
@patch("requests.request")
def test_temperature_cache_miss_fills_cache(mock_request, mock_s3, client):
    mock_request.return_value = make_response(
        HTTPStatus.OK, fresh_box_payload(value=6.77)
    )

    response = client.get("/temperature")

    assert response.status_code == HTTPStatus.OK
    assert json.loads(valkey_client.get(name="avg-temp")) == response.json
    assert 0 < valkey_client.ttl(name="avg-temp") <= app_module.CYCLE_SECONDS
    mock_s3.put_object.assert_called_once()


@patch("app.OpenSenseMap")
@patch("app.s3_client")
def test_temperature_refreshes_when_cache_entry_expired(
    mock_s3, mock_api_class, client
):
    old_value = json.dumps({"avg_temp": 12.5, "status": "Good"})
    valkey_client.set(name="avg-temp", value=old_value, px=1)
    time.sleep(0.05)
    mock_api_class.return_value.get_avg_temperature.return_value = OK_RESULT

    response = client.get("/temperature")

    assert response.json == {"avg_temp": 6.77, "status": "Too Cold"}
    mock_s3.put_object.assert_called_once()


@patch("app.OpenSenseMap")
@patch("app.s3_client")
def test_temperature_ignores_invalid_cache_entry(mock_s3, mock_api_class, client):
    valkey_client.set(name="avg-temp", value="{'avg_temp': 12.5}", ex=300)
    mock_api_class.return_value.get_avg_temperature.return_value = OK_RESULT

    response = client.get("/temperature")

    assert response.json == {"avg_temp": 6.77, "status": "Too Cold"}
    assert json.loads(valkey_client.get(name="avg-temp")) == response.json
    mock_s3.put_object.assert_called_once()


@pytest.mark.parametrize("failure", FAILURES)
@patch("app.s3_client")
@patch("requests.request")
def test_temperature_returns_500_when_all_senseboxes_fail(
    mock_request, mock_s3, client, failure
):
    mock_request.side_effect = failure

    response = client.get("/temperature")

    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert response.json == {"avg_temp": 0, "status": "Internal Error"}
    assert valkey_client.get(name="avg-temp") is None
    assert metric_value("failed_sensebox_count") == len(app_module.senseBoxes)
    mock_s3.put_object.assert_called_once()


@patch("app.s3_client")
@patch("requests.request")
def test_temperature_returns_500_when_all_measurements_are_stale(
    mock_request, mock_s3, client
):
    mock_request.return_value = make_response(
        HTTPStatus.OK, fresh_box_payload(age=timedelta(hours=2))
    )

    response = client.get("/temperature")

    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert metric_value("failed_sensebox_count") == len(app_module.senseBoxes)
    mock_s3.put_object.assert_called_once()


@patch("app.s3_client")
@patch("requests.request")
def test_temperature_with_some_senseboxes_failing(mock_request, mock_s3, client):
    total = len(app_module.senseBoxes)
    failing = 2
    good = make_response(HTTPStatus.OK, fresh_box_payload(value=20.0))
    bad = make_response(HTTPStatus.NOT_FOUND)
    mock_request.side_effect = [bad] * failing + [good] * (total - failing)

    response = client.get("/temperature")

    assert response.status_code == HTTPStatus.OK
    assert response.json == {"avg_temp": 20.0, "status": "Good"}
    assert metric_value("failed_sensebox_count") == failing
    mock_s3.put_object.assert_called_once()


# --- /metrics: counters ---


def test_version_request_increments_counter(client):
    before = metric_value("version_requests_total")

    client.get("/version")

    assert metric_value("version_requests_total") == before + 1


def test_temperature_request_increments_counter_on_cache_hit(client):
    valkey_client.set(
        name="avg-temp",
        value=json.dumps({"avg_temp": 12.5, "status": "Good"}),
        ex=300,
    )
    before = metric_value("temp_requests_total")

    client.get("/temperature")

    assert metric_value("temp_requests_total") == before + 1


@patch("app.OpenSenseMap")
@patch("app.s3_client")
def test_store_request_increments_counter(mock_s3, mock_api_class, client):
    mock_api_class.return_value.get_avg_temperature.return_value = OK_RESULT
    before = metric_value("store_requests_total")

    client.get("/store")

    assert metric_value("store_requests_total") == before + 1
    mock_s3.put_object.assert_called_once()


# --- Valkey error path ---


@patch("app.valkey_client")
@patch("app.OpenSenseMap")
@patch("app.s3_client")
def test_store_returns_503_when_cache_is_down(
    mock_s3, mock_api_class, mock_valkey, client
):
    mock_api_class.return_value.get_avg_temperature.return_value = OK_RESULT
    mock_valkey.set.side_effect = ValkeyError("cache down")

    response = client.get("/store")

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.json == {"error": "cache unavailable"}
    mock_s3.put_object.assert_called_once()


# --- RustFS error path ---


@patch("app.OpenSenseMap")
@patch("app.s3_client")
def test_temperature_still_works_when_storage_is_down(mock_s3, mock_api_class, client):
    mock_api_class.return_value.get_avg_temperature.return_value = OK_RESULT
    mock_s3.put_object.side_effect = ClientError(
        {"Error": {"Code": "500", "Message": "down"}}, "PutObject"
    )

    response = client.get("/temperature")

    assert response.status_code == HTTPStatus.OK
    assert response.json == {"avg_temp": 6.77, "status": "Too Cold"}
    assert valkey_client.get(name="avg-temp") is not None


@patch("app.OpenSenseMap")
@patch("app.s3_client")
def test_store_returns_503_on_storage_connection_error(mock_s3, mock_api_class, client):
    mock_api_class.return_value.get_avg_temperature.return_value = OK_RESULT
    mock_s3.put_object.side_effect = EndpointConnectionError(
        endpoint_url="http://rustfs:9000"
    )

    response = client.get("/store")

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.json == {"error": "object storage unavailable"}
    assert valkey_client.get(name="avg-temp") is None


@patch("app.ensure_bucket")
def test_failed_bucket_setup_is_logged_not_raised(mock_ensure, caplog):
    mock_ensure.side_effect = EndpointConnectionError(endpoint_url="http://rustfs:9000")
    run = app_module._try_ensure_bucket  # pylint: disable=protected-access

    with caplog.at_level(logging.WARNING):
        run()

    assert "Object storage is not ready" in caplog.text


# --- /cache ---


@patch("app.s3_client")
@patch("app.OpenSenseMap")
def test_cache_updates_valkey_only(mock_api_class, mock_s3, client):
    mock_api_class.return_value.get_avg_temperature.return_value = OK_RESULT

    response = client.get("/cache")

    assert response.status_code == HTTPStatus.OK
    assert response.json == {"avg_temp": 6.77, "status": "Too Cold"}
    assert json.loads(valkey_client.get(name="avg-temp")) == response.json
    assert 0 < valkey_client.ttl(name="avg-temp") <= app_module.CYCLE_SECONDS
    mock_s3.put_object.assert_not_called()


@patch("app.s3_client")
@patch("app.OpenSenseMap")
def test_cache_replaces_an_existing_entry(mock_api_class, mock_s3, client):
    old_value = json.dumps({"avg_temp": 12.5, "status": "Good"})
    valkey_client.set(name="avg-temp", value=old_value, ex=300)
    mock_api_class.return_value.get_avg_temperature.return_value = OK_RESULT

    client.get("/cache")

    assert json.loads(valkey_client.get(name="avg-temp")) == {
        "avg_temp": 6.77,
        "status": "Too Cold",
    }
    mock_s3.put_object.assert_not_called()


@patch("app.s3_client")
@patch("app.OpenSenseMap")
def test_cache_sets_only_the_cache_timestamp(
    mock_api_class, mock_s3, client, monkeypatch
):
    mock_api_class.return_value.get_avg_temperature.return_value = OK_RESULT
    monkeypatch.setattr(app_module, "LAST_CACHE_REFRESH", 0.0)
    monkeypatch.setattr(app_module, "LAST_STORE_WRITE", 0.0)
    store_gauge_before = metric_value("store_last_write_timestamp_seconds")

    before = time.time()
    client.get("/cache")
    after = time.time()

    assert before <= app_module.LAST_CACHE_REFRESH <= after
    assert before <= metric_value("cache_last_refresh_timestamp_seconds") <= after
    assert app_module.LAST_STORE_WRITE == 0.0
    assert metric_value("store_last_write_timestamp_seconds") == store_gauge_before
    mock_s3.put_object.assert_not_called()


@patch("app.s3_client")
@patch("app.OpenSenseMap")
def test_cache_returns_500_and_keeps_old_entry_when_all_senseboxes_fail(
    mock_api_class, mock_s3, client
):
    old_value = json.dumps({"avg_temp": 12.5, "status": "Good"})
    valkey_client.set(name="avg-temp", value=old_value, ex=300)
    mock_api_class.return_value.get_avg_temperature.return_value = (
        {"avg_temp": 0, "status": "Internal Error"},
        HTTPStatus.INTERNAL_SERVER_ERROR,
        len(app_module.senseBoxes),
    )

    response = client.get("/cache")

    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert response.json == {"avg_temp": 0, "status": "Internal Error"}
    assert valkey_client.get(name="avg-temp").decode(encoding="UTF-8") == old_value
    mock_s3.put_object.assert_not_called()


@patch("app.valkey_client")
@patch("app.s3_client")
@patch("app.OpenSenseMap")
def test_cache_returns_503_when_cache_is_down(
    mock_api_class, mock_s3, mock_valkey, client
):
    mock_api_class.return_value.get_avg_temperature.return_value = OK_RESULT
    mock_valkey.set.side_effect = ValkeyError("cache down")

    response = client.get("/cache")

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.json == {"error": "cache unavailable"}
    mock_s3.put_object.assert_not_called()


@patch("app.s3_client")
@patch("app.OpenSenseMap")
def test_cache_records_failed_sensebox_count(mock_api_class, mock_s3, client):
    mock_api_class.return_value.get_avg_temperature.return_value = (
        {"avg_temp": 6.77, "status": "Too Cold"},
        HTTPStatus.OK,
        2,
    )

    client.get("/cache")

    assert metric_value("failed_sensebox_count") == 2
    mock_s3.put_object.assert_not_called()


@patch("app.s3_client")
@patch("app.OpenSenseMap")
def test_cache_request_increments_counter(mock_api_class, mock_s3, client):
    mock_api_class.return_value.get_avg_temperature.return_value = OK_RESULT
    before = metric_value("cache_requests_total")

    client.get("/cache")

    assert metric_value("cache_requests_total") == before + 1
    mock_s3.put_object.assert_not_called()


class StopScheduler(Exception):
    """Raised by the fake sleep to end the scheduler loop in a test."""


@patch("app.time")
@patch("app.refresh_cache")
@patch("app._try_ensure_bucket")
def test_scheduler_survives_a_failed_refresh(mock_ensure, mock_refresh, mock_time):
    mock_refresh.side_effect = [RuntimeError("boom"), (OK_RESULT[0], HTTPStatus.OK)]
    mock_time.sleep.side_effect = [None, StopScheduler()]

    with pytest.raises(StopScheduler):
        app_module.run_scheduler()

    assert mock_refresh.call_count == 2
    mock_ensure.assert_called_once()
    mock_time.sleep.assert_called_with(app_module.CYCLE_SECONDS)
