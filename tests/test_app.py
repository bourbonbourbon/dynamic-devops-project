# pylint: disable=missing-module-docstring
# pylint: disable=missing-function-docstring
# pylint: disable=redefined-outer-name
import json
from http import HTTPStatus
from unittest.mock import patch

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


@patch("requests.request")
def test_temperature_success(mock_request, client):
    with open(file="tests/weather.json", mode="r", encoding="UTF-8") as f:
        mock_request.return_value.status_code = HTTPStatus.OK
        mock_request.return_value.json.return_value = json.load(f)
        response = client.get("/temperature")
        assert response.status_code == HTTPStatus.OK
        assert response.json == {"avg_temp": 6.77, "status": "Too Cold"}


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