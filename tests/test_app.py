# pylint: disable=missing-module-docstring
# pylint: disable=missing-function-docstring
# pylint: disable=missing-class-docstring
# pylint: disable=wrong-import-position
# pylint: disable=redefined-outer-name
import sys
import os
from http import HTTPStatus
import json
from unittest.mock import patch
import pytest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from version import __version__


@pytest.fixture
def client():
    with app.test_client() as client_var:
        yield client_var


def test_version_success(client):
    response = client.get("/version")
    assert response.status_code == HTTPStatus.OK
    assert response.json == {"version": __version__}


@pytest.fixture()
def mock_response():
    with patch("requests.request") as mock_req:
        yield mock_req

def test_temperature_success(mock_response, client):
    with open("tests/weather.json", encoding="UTF-8") as f:
        mock_response.return_value.status_code = HTTPStatus.OK
        mock_response.return_value.json.return_value = json.load(f)
        response = client.get("/temperature")
        assert response.status_code == HTTPStatus.OK
        assert response.json == ({"avg_temp": 6.77, "status": "Too Cold"})

# write failure tests
# /metrics
