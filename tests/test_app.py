# pylint: disable=missing-module-docstring
# pylint: disable=missing-function-docstring
# pylint: disable=missing-class-docstring
# pylint: disable=wrong-import-position
# pylint: disable=redefined-outer-name
import sys
import os
import datetime
from unittest.mock import Mock
import pytest

# Add the parent directory to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from version import __version__


@pytest.fixture
def client():
    with app.test_client() as client_var:
        yield client_var


def test_version_success(client):
    response = client.get("/version")
    assert response.status_code == 200
    assert response.json == {"version": __version__}


def test_temperature_success(monkeypatch, client):
    mock_datetime = Mock()
    mock_datetime.now.return_value = datetime.datetime(2025, 1, 15, 0, 0, 0)
    monkeypatch.setattr("datetime.datetime", mock_datetime)
    response = client.get("/temperature")
    assert response.status_code == 200
    assert response.json == {"avg_temp": 19.71}
