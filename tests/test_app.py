# pylint: disable=missing-module-docstring
# pylint: disable=missing-function-docstring
# pylint: disable=redefined-outer-name
import json
from http import HTTPStatus
from unittest.mock import patch
from datetime import datetime, timedelta, timezone

import pytest
from botocore.exceptions import ClientError

from app import app, bucket_name, ensure_bucket, object_name, valkey_client
from version import __version__
from services.opensensemap import OpenSenseMap


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

    result = api._process_temperature_data(data, now=now) # pylint: disable=protected-access
    assert result is None


def test_measurement_within_one_hour_is_accepted():
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    data = fresh_box_payload(value=20.5, age=timedelta(minutes=0))
    data["sensors"][0]["lastMeasurement"]["createdAt"] = "2026-01-01T11:30:00.000Z"

    api = OpenSenseMap(base_url="https://example.test")

    result = api._process_temperature_data(data, now=now)  # pylint: disable=protected-access
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
