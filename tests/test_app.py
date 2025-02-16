# pylint: disable=missing-module-docstring
# pylint: disable=missing-function-docstring
# pylint: disable=missing-class-docstring
# pylint: disable=wrong-import-position
# pylint: disable=redefined-outer-name
import sys
import os
import datetime
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
    assert response.status_code == 200
    assert response.json == {"version": __version__}


# https://stackoverflow.com/a/73476629
class MockedDatetime(datetime.datetime):
    @classmethod
    def now(cls):
        return datetime.datetime(2025, 1, 15, 0, 0, 0)


def test_temperature_success(monkeypatch, client):
    with monkeypatch.context() as mpc:
        mpc.setattr(datetime, "datetime", MockedDatetime)
        response = client.get("/temperature")
        assert response.status_code == 200
        assert response.json == {"avg_temp": 19.71}
