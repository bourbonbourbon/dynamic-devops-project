# dynamic-devops-project
[![Dynamic DevOps Roadmap](https://devopshive.net/badges/dynamic-devops-roadmap.svg)](https://github.com/DevOpsHiveHQ/dynamic-devops-roadmap)

[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/bourbonbourbon/dynamic-devops-project/badge)](https://scorecard.dev/viewer/?uri=github.com/bourbonbourbon/dynamic-devops-project)

[![CI](https://github.com/bourbonbourbon/dynamic-devops-project/actions/workflows/main.yml/badge.svg)](https://github.com/bourbonbourbon/dynamic-devops-project/actions/workflows/main.yml)

[![OpenSSF Best Practices](https://www.bestpractices.dev/projects/16984/badge)](https://www.bestpractices.dev/projects/16984)

# HiveBox (ddp)

HiveBox is a small Python web service. It is my implementation of the
[HiveBox project](https://devopsroadmap.io/projects/hivebox/) from DevOps Roadmap.

The service reads temperature data from [openSenseMap](https://opensensemap.org)
senseBoxes. It calculates the average temperature and gives it a status:
`Too Cold`, `Good`, or `Too Hot`.

Current version: `0.4.4` (see `src/version.py`).

## How it works

1. A background thread runs one refresh cycle every 300 seconds.
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
| `GET /version` | Returns the application version. | `200` `{"version": "0.4.4"}` | - |
| `GET /temperature` | Returns the average temperature from the cache. On a cache miss, it fetches new data. | `200` `{"avg_temp": 14.98, "status": "Good"}` | `500` when no senseBox gives a reading. `503` when Valkey is not available. |
| `GET /store` | Fetches new data and writes it to RustFS and to the cache. | `200` (same body as `/temperature`) | `503` `{"error": "object storage unavailable"}` when the RustFS write fails. |
| `GET /cache` | Fetches new data and writes it to the Valkey cache only. Does not use RustFS. | `200` (same body as `/temperature`) | `500` when no senseBox gives a reading. `503` when Valkey is not available. |
| `GET /readyz` | Readiness check. | `200` | `503` when a check fails. |
| `GET /metrics` | Prometheus metrics. | `200` | - |

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
| `cache_requests_total` | counter | Number of `/cache` requests. |
| `cache_last_refresh_timestamp_seconds` | gauge | Unix time of the last successful cache write. |
| `store_last_write_timestamp_seconds` | gauge | Unix time of the last successful RustFS write. |
| `failed_sensebox_count` | gauge | Number of failed senseBoxes in the last refresh. |

Prometheus calculates the age at query time:

- Cache age in seconds: `time() - cache_last_refresh_timestamp_seconds`
- Store age in seconds: `time() - store_last_write_timestamp_seconds`

## Configuration

The service reads its settings from environment variables.
Environment variables take precedence over the `.env` file in the project root.
Kubernetes and CI pass their values as environment variables.

| Variable | Description | Example |
|---|---|---|
| `PORT` | Port of the web server. | `8080` |
| `HOST` | Address of the web server. | `0.0.0.0` |
| `SENSEBOXES` | senseBox IDs, separated by commas. | `5eba5fbad46fb8001b799786,5a77184229b729001a150c10` |
| `S3_ENDPOINT_URL` | URL of the S3-compatible storage (RustFS). | `http://localhost:9000` |
| `S3_ACCESS_KEY` | Access key of the storage. You can also set `S3_ACCESS_KEY_FILE` to a file path. | `ROOTUSER` |
| `S3_SECRET_KEY` | Secret key of the storage. You can also set `S3_SECRET_KEY_FILE` to a file path. | (set your own value) |
| `S3_BUCKET` | Bucket name. The service creates the bucket if it does not exist. | `avg-temp` |
| `S3_OBJECT` | Object name in the bucket. | `avg-temp` |
| `S3_REGION` | Region name for the S3 client. Optional. Default: `us-east-1`. | `us-east-1` |
| `VKURL` | Host name of Valkey. | `localhost` |
| `VKPORT` | Port of Valkey. | `6379` |

All variables are required except `S3_REGION`. The service fails at startup when a required variable is missing.

> **Warning:** Do not commit the `.env` file. It is listed in `.gitignore` and `.dockerignore`.
> Use placeholder values in `.env.example`. Use real secrets only in your local `.env`,
> in CI secrets, or in Kubernetes Secrets.

## Requirements

- Python 3.14
- Docker (for Valkey, RustFS, and the image build)
- `kubectl` and `kind` (for the Kubernetes steps)

## Run locally

1. Create a virtual environment and install the packages:

   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install --require-hashes -r requirements-test.txt
   ```

2. Create a `.env` file from `.env.example`. Set `VKURL=localhost` and
   `S3_ENDPOINT_URL=http://localhost:9000`. Set your own `S3_SECRET_KEY`.

3. Start Valkey:

   ```bash
   docker run -d --name valkey -p 6379:6379 valkey/valkey:latest
   ```

4. Start RustFS. Use a pinned tag from
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

5. Start the application:

   ```bash
   python src/app.py
   ```

6. Test the endpoints:

   ```bash
   curl -i http://localhost:8080/version
   curl -i http://localhost:8080/temperature
   curl -i http://localhost:8080/readyz
   curl -s http://localhost:8080/metrics
   ```

## Run with Docker Compose

Docker Compose starts the app, Valkey, and RustFS together. The app runs in its
container, so you do not need a Python environment on your machine.

1. Create the `.env` file from `.env.example`. Set `S3_ACCESS_KEY` and `S3_SECRET_KEY`.
   Compose stops with an error if these values are missing.

2. Start the stack:

   ```bash
   docker compose up -d --build
   ```

3. Check the status. The `app` service must show `healthy` after about one minute:

   ```bash
   docker compose ps
   ```

4. Call the endpoints:

   ```bash
   curl -i http://localhost:8080/version
   curl -i http://localhost:8080/store
   ```

5. Stop the stack. The data in RustFS is kept:

   ```bash
   docker compose down
   ```

   To delete the stored data too, run `docker compose down -v`.

Inside the Compose network, the app reaches the services by their names, `valkey` and
`rustfs`. The values in `.env` for `localhost` apply only to runs outside Compose.

## Tests

The tests use `pytest`. The settings are in `pytest.ini`.
By default, `pytest.ini` skips the integration tests (`-m "not integration"`).

The tests need the same environment variables as the application. Create `.env` first
(see Run locally, step 2). `src/app.py` reads its configuration when it is imported.

### Unit tests

The unit tests in `tests/test_app.py` and `tests/test_*.py` mock RustFS and the openSenseMap API.
They use a real Valkey server on `localhost:6379`. Start Valkey before you run them.

> **Warning:** The unit tests run `FLUSHDB` on Valkey before each test. They delete all keys
> in database 0. Use a disposable Valkey container.

Run the unit tests with a coverage report:

```bash
pytest --cov --cov-report=term-missing
```

### Integration tests

The integration tests are in `tests/integration/`. They use real Valkey and RustFS
containers. They mock only the openSenseMap API.

Run them with the marker:

```bash
pytest -m integration -v
```

> **Warning:** The integration tests delete all keys in Valkey database 0. They also delete
> the stored object in the bucket. They use `S3_BUCKET` for the stored object and create
> temporary buckets with random names. Use disposable containers only. Set `S3_BUCKET` to a
> test bucket name when you run them on your own machine.

CI runs the integration tests in the job `integration-tests`.

### Coverage

The minimum total coverage is 90 percent. The value is `fail_under` in `.coveragerc`.
The pytest step fails when coverage is below this value. The CI summary step writes
the report to the job summary and does not check the threshold.

### Lint and format

Run the linter. CI fails below a score of 9. The settings are in `.pylintrc`:

```bash
PYTHONPATH=src pylint --fail-under=9 src tests
```

Format the code before you commit:

```bash
isort src tests
black src tests
```

The file `.isort.cfg` sets `profile = black`. With this setting, isort and black do not change each other's output.

Check the Dockerfile with Hadolint:

```bash
docker run --rm -i hadolint/hadolint < Dockerfile
```

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

The container runs as the user `nobody` (UID 65534). It uses `tini` as the init process.
The image does not contain the `.env` file.
The container must reach Valkey and RustFS at the addresses in `.env`.
Use a Docker network, or set the variables with `-e`, when you run all
three containers on one host.

CI pushes the image to `ghcr.io/bourbonbourbon/ddp:<version>`.

## Kubernetes

The folder `k8s/` contains the manifests. `k8s/kustomization.yml` lists all resources.

| Path | Content |
|---|---|
| `kind.yaml` (repository root) | Configuration of the local KIND cluster. Maps ports 80 and 443 to the host. |
| `k8s/ddp-namespace.yml` | Namespace `ddp`. |
| `k8s/ddp-secrets.yml` | Secret `rustfs-credentials` for local tests. See the warning below. |
| `k8s/ddp/` | ConfigMap, Deployment, Service, and NetworkPolicy of the application. |
| `k8s/rustfs/` | PersistentVolume, PersistentVolumeClaim, Deployment, Service, and NetworkPolicy of RustFS. |
| `k8s/valkey/` | Deployment, Service, and NetworkPolicy of Valkey. |

The NetworkPolicies allow only these paths:

- Ingress to the application on port `8080`.
- The application to Valkey on port `6379`.
- The application to RustFS on port `9000`.
- The application to DNS and to public addresses on port `443`.

### Local KIND setup

1. Create the cluster:

   ```bash
   kind create cluster --config kind.yaml
   ```

2. Remove `ddp-secrets.yml` from `k8s/kustomization.yml`. Then create the Secret yourself.
   Use your own values:

   ```bash
   kubectl create namespace ddp
   kubectl -n ddp create secret generic rustfs-credentials \
     --from-literal=RUSTFS_ACCESS_KEY=ROOTUSER \
     --from-literal=RUSTFS_SECRET_KEY='<your-secret>'
   ```

   > **Warning:** The file `k8s/ddp-secrets.yml` stores the values as base64. Base64 is not
   > encryption. Do not commit real secret values. Use `kubectl create secret`, or a tool
   > such as Sealed Secrets, for real values.

3. Apply the manifests:

   ```bash
   kubectl apply -k k8s/
   ```

4. Check the pods. The application pod becomes ready after the first refresh cycle:

   ```bash
   kubectl -n ddp get pods
   ```

5. Open the application from your computer:

   ```bash
   kubectl -n ddp port-forward svc/ddp-service 8080:80
   curl -i http://localhost:8080/version
   ```

   Port-forward works without a load balancer. The service type is `LoadBalancer`.
   On KIND, a `LoadBalancer` service stays in `<pending>` until you install a load
   balancer implementation, such as cloud-provider-kind or MetalLB.

The deployment uses the image `ghcr.io/bourbonbourbon/ddp:0.4.4`. The image must exist in GHCR.
To use a local image, change the image name in `k8s/ddp/ddp-deployment.yml`, load the
image into KIND with `kind load docker-image ddp:test`, and set `imagePullPolicy` to `IfNotPresent`.

### Limitations of the KIND setup

- **RustFS storage uses `hostPath`.** The PersistentVolume stores data at `/mnt/data`
  on the KIND node. It works only on one node. The data stays on that node and is lost
  when the KIND cluster is deleted. This is acceptable for a test. Do not use it in production.
  The path is inside the KIND node container, not on your computer.
- **Valkey has no persistent storage.** The Valkey deployment uses an `emptyDir` volume.
  The cache is empty after a pod restart. The service refills the cache on the next refresh.
- **The Valkey manifests are in `k8s/valkey/`.** The Valkey service name is `valkey-service`.
- **The service type is `LoadBalancer`.** See the local KIND setup above.
- **The Secret file is for local tests only.** Replace it before you use the cluster for anything else.

## CI

The workflow `.github/workflows/main.yml` runs on each push to `main`.
The jobs run in this order:

1. `lint`: runs pylint and Hadolint.
2. `unittests`: starts Valkey and RustFS with Compose, and runs pytest with coverage.
3. `integration-tests`: starts Valkey and RustFS with Compose, and runs the integration tests.
4. `build`: builds the image and pushes it to GHCR. It runs after the test jobs.
5. `version-check`: runs the image and compares `/version` with `src/version.py`.

Two more workflows run security checks:

- `scorecard.yml`: OpenSSF Scorecard analysis.
- `terrascan.yml`: Terrascan scan of the files in `k8s/`.

CI reads the `.env` file from the repository secret `DOTENV`.

## Project layout

```
.
├── .github/workflows/        CI and security workflows
├── k8s/                      Kubernetes manifests (kustomization.yml, ddp/, rustfs/, valkey/)
├── src/
│   ├── app.py                Flask application, scheduler, and endpoints
│   ├── version.py            Application version
│   └── services/
│       └── opensensemap.py   Client for the openSenseMap API
├── tests/
│   ├── integration/          Integration tests with real Valkey and RustFS
│   └── test_app.py           Unit tests
├── Dockerfile
├── docker-compose.yml
├── kind.yaml                 KIND cluster configuration
├── pytest.ini
├── .coveragerc
├── requirements.txt          Runtime packages (hashes)
└── requirements-test.txt     Test and lint packages (hashes)
```

## Known limitations

- Each application instance has its own scheduler and its own readiness data.
- If Valkey is not available, `/temperature` returns `503`. It does not fetch data directly.
- The service stores error results in RustFS. It does not store them in Valkey.
- The Kubernetes storage uses `hostPath`. See the KIND limitations above.

## Project status

Done:

- [x] `/version`, `/temperature`, `/store`, `/cache`, `/readyz`, and `/metrics` endpoints
- [x] Valkey cache and RustFS storage (S3 API with `boto3`)
- [x] Background scheduler (no cron)
- [x] Custom Prometheus metrics
- [x] Unit tests, integration tests, pylint, and Hadolint in CI
- [x] Docker image on GHCR
- [x] OpenSSF Scorecard and Terrascan workflows
- [x] Docker Compose for the app, Valkey, and RustFS
- [x] Kubernetes manifests for the application, RustFS, and Valkey

Open:

- [ ] Helm chart and Kustomize manifests for the infrastructure
- [ ] Remove the test Secret file from Git and use a Secret tool for real values
- [ ] Persistent storage for RustFS and Valkey on a real cluster
- [ ] Image scanning (Trivy), SonarQube or Semgrep, Dependabot alerts
- [ ] Build job only on `main` or on version tags
- [ ] Terraform for the Kubernetes cluster
- [ ] Grafana for logs and metrics
- [ ] End-to-end tests with Venom
- [ ] Continuous delivery with Argo CD, ExternalDNS, and Cert-Manager

## License

This project is licensed under the MIT License. See `LICENSE`.

## Security

See `SECURITY.md` for how to report a vulnerability.