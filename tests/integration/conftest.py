# pylint: disable=missing-module-docstring
# pylint: disable=missing-function-docstring
# pylint: disable=redefined-outer-name
import pytest
from botocore.exceptions import BotoCoreError, ClientError
from valkey.exceptions import ValkeyError

import app as app_module


@pytest.fixture(scope="session", autouse=True)
def real_services():
    """Stop early with a clear message when a service is not ready."""
    try:
        app_module.valkey_client.ping()
    except ValkeyError as err:
        pytest.fail(f"Valkey is not reachable: {err}", pytrace=False)
    try:
        app_module.ensure_bucket()
    except (BotoCoreError, ClientError) as err:
        pytest.fail(
            f"RustFS is not ready or rejects the credentials: {err}", pytrace=False
        )


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    """Give each test an empty cache, an empty bucket, and a fresh app state."""
    app_module.valkey_client.flushdb()
    app_module.s3_client.delete_object(
        Bucket=app_module.bucket_name, Key=app_module.object_name
    )
    monkeypatch.setattr(app_module, "LAST_CACHE_REFRESH", 0.0)
    monkeypatch.setattr(app_module, "LAST_STORE_WRITE", 0.0)
    monkeypatch.setattr(app_module, "SENSEBOX_FAIL_COUNT", 0)


@pytest.fixture
def client():
    with app_module.app.test_client() as client_var:
        yield client_var
