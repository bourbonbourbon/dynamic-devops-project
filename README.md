# dynamic-devops-project
[![Dynamic DevOps Roadmap](https://devopshive.net/badges/dynamic-devops-roadmap.svg)](https://github.com/DevOpsHiveHQ/dynamic-devops-roadmap)

[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/bourbonbourbon/dynamic-devops-project/badge)](https://scorecard.dev/viewer/?uri=github.com/bourbonbourbon/dynamic-devops-project)

[![CI](https://github.com/bourbonbourbon/dynamic-devops-project/actions/workflows/main.yml/badge.svg)](https://github.com/bourbonbourbon/dynamic-devops-project/actions/workflows/main.yml)

# HiveBox (ddp)

HiveBox is a small Python web service. It is my implementation of the
[HiveBox project](https://devopsroadmap.io/projects/hivebox/) from DevOps Roadmap.

The service reads temperature data from [openSenseMap](https://opensensemap.org)
senseBoxes. It calculates the average temperature and gives it a status:
`Too Cold`, `Good`, or `Too Hot`.

Current version: `0.4.0` (see `src/version.py`).

## How it works

1. A background thread runs every 300 seconds (one cycle).
2. The thread requests the data of each senseBox from the openSenseMap API.
3. The service uses only a temperature sensor that:
   - has the icon `osem-thermometer`
   - has the unit `°C`
   - has a measurement that is not older than one hour (compared in UTC)
4. The service calculates the average and rounds it to two decimals.
5. The service writes the result as JSON to:
   - RustFS (S3-compatible object storage), as a stored copy
   - Valkey, as a cache with a lifetime of 300 seconds
6. The service does not cache error results.

A senseBox that gives no usable reading counts as a failed senseBox.
The service writes one warning to the log for each failed senseBox.

### Status rules

| Average temperature | Status |
|---|---|
| 10 or lower | `Too Cold` |
| Above 10, up to and including 36 | `Good` |
| Above 36 | `Too Hot` |

The service rounds the average first. Then it selects the status.

## Endpoints

| Endpoint | Description | Success | Failure |
|---|---|---|---|
| `GET /version` | Returns the application version. | `200` `{"version": "0.4.0"}` | - |
| `GET /temperature` | Returns the average temperature from the cache. On a cache miss, it fetches new data. | `200` `{"avg_temp": 14.98, "status": "Good"}` | `500` when no senseBox gives a reading. `503` when Valkey is not available. |
| `GET /store` | Fetches new data and writes it to RustFS and to the cache. | `200` (same body as `/temperature`) | `503` `{"error": "object storage unavailable"}` when the RustFS write fails. |
| `GET /readyz` | Readiness check. | `200` | `503` when a check fails. |
| `GET /metrics` | Prometheus metrics. | `200` | - |
| `GET /cache` | Fetches new data and writes it to the Valkey cache only. Does not use RustFS. | `200` (same body as `/temperature`) | `500` when no senseBox gives a reading. `503` when Valkey is not available. |

### Readiness (`/readyz`)

The endpoint returns `200` only when all these conditions are true:

- At least half of the senseBoxes, plus one, are reachable.
- The last successful cache write is not older than two cycles (600 seconds).
- The last successful RustFS write is not older than two cycles (600 seconds).

The response body shows each check. Example:

```json
{
  "ready": true,
  "checks": {
    "senseboxes_reachable": true,
    "cache_fresh": true,
    "store_fresh": true
  },
  "reachable_senseboxes": 6
}
```

The endpoint returns `503` before the first successful refresh.

### Metrics (`/metrics`)

The service exports the default Python metrics and these custom metrics:

| Metric | Type | Description |
|---|---|---|
| `version_requests_total` | counter | Number of `/version` requests. |
| `temp_requests_total` | counter | Number of `/temperature` requests (cache hits and misses). |
| `store_requests_total` | counter | Number of `/store` requests. |
| `cache_last_refresh_timestamp_seconds` | gauge | Unix time of the last successful cache write. |
| `store_last_write_timestamp_seconds` | gauge | Unix time of the last successful RustFS write. |
| `failed_sensebox_count` | gauge | Number of failed senseBoxes in the last refresh. |
| `cache_requests_total` | counter | Number of `/cache` requests. |

Prometheus calculates the age at query time:

- Cache age in seconds: `time() - cache_last_refresh_timestamp_seconds`
- Store age in seconds: `time() - store_last_write_timestamp_seconds`

## Configuration

The service reads its settings from environment variables.
If a variable is not set, the service reads it from the `.env` file in the project root.

| Variable | Description | Example |
|---|---|---|
| `PORT` | Port of the web server. | `8080` |
| `HOST` | Address of the web server. | `0.0.0.0` |
| `SENSEBOXES` | senseBox IDs, separated by commas. | `5eba5fbad46fb8001b799786,5a77184229b729001a150c10` |
| `S3_ENDPOINT_URL` | URL of the S3-compatible storage (RustFS). | `http://localhost:9000` |
| `S3_ACCESS_KEY` | Access key of the storage. | `ROOTUSER` |
| `S3_SECRET_KEY` | Secret key of the storage. | (set your own value) |
| `S3_BUCKET` | Bucket name. The service creates the bucket if it does not exist. | `avg-temp` |
| `S3_OBJECT` | Object name in the bucket. | `avg-temp` |
| `S3_REGION` | Region name for the S3 client. Optional. Default: `us-east-1`. | `us-east-1` |
| `VKURL` | Host name of Valkey. | `localhost` |
| `VKPORT` | Port of Valkey. | `6379` |

> **Warning:** The `.env` file is in the repository and the Dockerfile copies it
> into the image. Use only placeholder values in this file. Do not use real secrets.
> This will change when the configuration moves to Kubernetes Secrets.

## Requirements

- Python 3.12
- Docker (for Valkey, RustFS, and the image build)
- `kubectl` and `kind` (for the Kubernetes steps)

## Run locally

1. Create a virtual environment and install the packages:

   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements-dev.txt
   ```

2. Start Valkey:

   ```bash
   docker run -d --name valkey -p 6379:6379 valkey/valkey:latest
   ```

3. Start RustFS. Use a pinned tag from
   [Docker Hub](https://hub.docker.com/r/rustfs/rustfs) in place of `<rustfs-tag>`:

   ```bash
   docker run -d --name rustfs -p 9000:9000 -p 9001:9001 \
     -e RUSTFS_ACCESS_KEY=ROOTUSER \
     -e RUSTFS_SECRET_KEY=<your-secret> \
     -v "$(pwd)/rustfs-data:/data" \
     rustfs/rustfs:<rustfs-tag>
   ```

   Port `9000` is the S3 API. Port `9001` is the web console.
   Make sure the values in `.env` match the keys that you set here.
   Check the RustFS documentation for the variable names of your tag.

4. Start the application:

   ```bash
   python src/app.py
   ```

5. Test the endpoints:

   ```bash
   curl -i http://localhost:8080/version
   curl -i http://localhost:8080/temperature
   curl -i http://localhost:8080/readyz
   curl -s http://localhost:8080/metrics
   ```

## Test and lint

The unit tests mock RustFS and the openSenseMap API.
The unit tests use a real Valkey server on `localhost:6379`.
Start Valkey before you run the tests (see step 2 above).

Run the tests with a coverage report:

```bash
pytest --cov --cov-report=term-missing
```

CI fails when the total coverage is below the value `fail_under` in `.coveragerc`.

Run the linter:

```bash
pylint --fail-under=9 src tests
```

The file `pytest.ini` sets the import path for pytest.
The file `.pylintrc` sets the import path for pylint.

### Integration tests

The integration tests are in `tests/integration/`. They use real Valkey and RustFS
containers. They mock only the openSenseMap API.

A normal `pytest` run skips them. Run them with the marker:

```bash
pytest -m integration -v
```

> **Warning:** The tests delete all keys in Valkey database 0. They also delete the
> stored object in the bucket. Use disposable containers only. Set `S3_BUCKET` to a
> test bucket name when you run them on your own machine.

CI runs the integration tests in the job `integration-tests`.

## Tools

| Tool | Use | Command |
|---|---|---|
| [black](https://github.com/psf/black) | Formats the Python code. | `black src tests` |
| [isort](https://pycqa.github.io/isort/) | Sorts the imports. | `isort src tests` |
| [pylint](https://pylint.readthedocs.io) | Checks the code. CI fails below a score of 9. The settings are in `.pylintrc`. | `pylint --fail-under=9 src tests` |
| [pigar](https://github.com/damnever/pigar) | Generates `requirements.txt` from the imports in the code. | `pigar generate` |
| [pytest](https://docs.pytest.org) | Runs the tests. The settings are in `pytest.ini`. | `pytest` |
| pytest-cov | Measures the test coverage. The settings are in `.coveragerc`. | `pytest --cov` |
| [Hadolint](https://github.com/hadolint/hadolint) | Checks the Dockerfile. | `docker run --rm -i hadolint/hadolint < Dockerfile` |
| [Terrascan](https://github.com/tenable/terrascan) | Scans the Kubernetes manifests in `k8s/`. CI only. | - |
| [OpenSSF Scorecard](https://github.com/ossf/scorecard) | Checks the security practices of the repository. CI only. | - |
| Docker, KIND, kubectl | Run the containers and the local Kubernetes cluster. | - |

Format the code before you commit:

```bash
isort src tests
black src tests
```

The file `.isort.cfg` sets `profile = black`. With this setting, isort and black do not change each other's output.

The file `requirements.txt` contains the packages that the application needs.
The file `requirements-dev.txt` contains the packages for tests and linting.
Check `requirements.txt` after you run pigar. Pigar can add test packages to the file.


## Docker

Build the image:

```bash
docker build -t ddp:test --target prod .
```

Run the image:

```bash
docker run -d -p 8080:8080 --name ddp ddp:test
curl -s http://localhost:8080/version
```

The container runs as the user `nobody`.
The container must reach Valkey and RustFS at the addresses in `.env`.
Use a Docker network, or set the variables with `-e`, when you run all
three containers on one host.

CI pushes the image to `ghcr.io/bourbonbourbon/ddp:<version>`.

## Kubernetes

The folder `k8s/` contains these files:

| File | Content |
|---|---|
| `kind.yaml` | Configuration of the local KIND cluster. |
| `deploy-app.yml` | Pod, Service, and Ingress of the application. |
| `rustfs.yml` | PersistentVolumeClaim, Deployment, and Service of RustFS. |

Create the Secret for RustFS first. Do not put the values in a file in Git:

```bash
kubectl create secret generic rustfs-credentials \
  --from-literal=RUSTFS_ACCESS_KEY=ROOTUSER \
  --from-literal=RUSTFS_SECRET_KEY='<your-secret>'
```

Then apply the manifests:

```bash
kubectl apply -f k8s/rustfs.yml
kubectl apply -f k8s/deploy-app.yml
```

Before you apply `rustfs.yml`, replace `<rustfs-tag>` with a pinned image tag.

The application expects a Valkey service with the name `valkey-service`.
The repository does not have the Valkey manifests yet.

## CI

The workflow `.github/workflows/main.yml` runs on each push to `main`.
It has these jobs in this order:

1. `lint`: runs pylint and Hadolint.
2. `unittests`: starts Valkey and runs pytest.
3. `build`: builds the image and pushes it to GHCR.
4. `version-check`: runs the image and compares `/version` with `src/version.py`.

Two more workflows run security checks:

- `scorecard.yml`: OpenSSF Scorecard analysis.
- `terrascan.yml`: Terrascan scan of the files in `k8s/`.

## Project layout

```
.
├── .github/workflows/   CI and security workflows
├── k8s/                 Kubernetes manifests
├── src/
│   ├── app.py           Flask application, scheduler, and endpoints
│   ├── version.py       Application version
│   └── services/
│       └── opensensemap.py   Client for the openSenseMap API
├── tests/
│   └── test_app.py      Unit tests
├── Dockerfile
├── pytest.ini
├── requirements.txt
└── requirements-dev.txt
```

## Project status

Done:

- [x] `/version`, `/temperature`, `/store`, `/readyz`, and `/metrics` endpoints
- [x] Valkey cache and RustFS storage (S3 API with `boto3`)
- [x] Background scheduler (no cron)
- [x] Custom Prometheus metrics
- [x] Unit tests, pylint, and Hadolint in CI
- [x] Docker image on GHCR
- [x] OpenSSF Scorecard and Terrascan workflows

Open:

- [x] `/cache` endpoint
- [x] Integration tests with real Valkey and RustFS
- [ ] Replace the Pod with a Deployment, and add readiness and liveness probes
- [ ] Valkey manifests
- [ ] Helm chart and Kustomize manifests
- [ ] Remove `.env` from the repository and from the image
- [ ] Image scanning (Trivy), SonarQube or Semgrep, Dependabot
- [ ] Build job only on `main` or on version tags
- [ ] Terraform for the Kubernetes cluster
- [ ] Grafana for logs and metrics
- [ ] End-to-end tests with Venom
- [ ] Continuous delivery with Argo CD, ExternalDNS, and Cert-Manager

## Known limitations

- Each application instance has its own scheduler and its own readiness data.
- If Valkey is not available, `/temperature` returns `503`. It does not fetch data directly.
- The service stores error results in RustFS. It does not store them in Valkey.