## A. Remove all MinIO references

- [x] Run `grep -rni "minio" . --exclude-dir=.git` and fix every match.
- [ ] Find the current stable RustFS image tag on Docker Hub and in the RustFS documentation. Write the exact tag down.
- [x] Replace `minio==7.2.15` in `requirements.txt` with a pinned `boto3` version.
- [x] Create `requirements-dev.txt` with the test packages.
- [ ] Create `.env.example` with placeholder values.
- [x] Add `.env` and `rustfs-data/` to `.gitignore`.
- [x] Run `git rm --cached .env` so Git stops tracking the file.
- [ ] Change the MinIO password `CHANGEME123` on every system where it was used.
- [ ] Remove the committed `.env` from Git history (for example, with `git filter-repo`). This step is optional, but the old password stays in history until you do it.
- [x] Rewrite the storage code in `src/app.py` to use `boto3`.
- [x] Change the CI unit test job to start RustFS instead of MinIO.
- [x] Store the RustFS secret key in GitHub Actions secrets.
- [x] Add the RustFS Kubernetes manifests (Secret, PersistentVolumeClaim, Deployment, Service).
- [x] Change the README and `todo.txt` text from MinIO to RustFS.
- [x] Change section 5.2 of the README checklist to say RustFS.

## B. Move the code into `src/`

- [x] Run `mkdir src`.
- [x] Run `git mv app.py src/app.py`, `git mv version.py src/version.py`, and `git mv services src/services`.
- [x] Commit the move alone.
- [x] Change the `.env` path in `src/app.py` so it resolves from the file location.
- [x] Rewrite the Dockerfile so it copies `src/` and runs `./src/app.py`.
- [ ] Remove `COPY .env` from the Dockerfile.
- [x] Remove the commented-out `dev` stage from the Dockerfile, or restore it on purpose.
- [x] Create `pytest.ini` with `pythonpath = src` and `testpaths = tests`.
- [x] Remove the `sys.path.append` block from `tests/test_app.py`.
- [x] Update the pylint command in CI to `pylint --fail-under=9 src tests` with `PYTHONPATH: src`.
- [x] Update the version lookup paths in all CI jobs.
- [x] Update the local run command in the README.
- [x] Check that `.dockerignore` does not exclude `src/`.
- [x] Check that `.dockerignore` excludes `.git`, `venv`, `rustfs-data`, and `.env`.

## C. Fix the code bugs

- [x] Remove the storage connection from import time. Use the `ensure_bucket()` function at startup.
- [x] Read configuration from `os.environ` first, then from `.env`.
- [x] Skip `None` values in `_process_temperature_data` and count them as failed senseBoxes.
- [x] Stop the early `return` in `get_avg_temperature` when a request raises an exception. Count the failure and continue.
- [x] Do not cache `"Internal Error"` results.
- [x] Move `total_temp_requests.inc()` so it counts cache hits as well as misses.
- [x] Replace `ast.literal_eval` with `json.dumps` and `json.loads` for cached values.
- [x] Return a clear HTTP status (for example, 503) when Valkey or RustFS is unavailable. Do not return an unhandled exception.
- [x] Make the version check in CI fail with `exit 1` when the versions differ.
- [x] Remove the commented-out code in `src/app.py`.

## D. Meet the specification

- [x] Change the freshness window in `services/opensensemap.py` to one hour. Compare timestamps in UTC with timezone-aware datetime values.
- [x] Use a 5-minute cache cycle. Change `ex=3000` to `ex=300` or a value linked to the cycle.
- [x] Start a background scheduler in the app that stores the data every 5 minutes. Do not use cron.
- [x] Delete the `crontab` file.
- [x] Change `/temperature` so it reads from the cache. Refresh the cache only when the data is stale.
- [x] Add the `/cache` endpoint. It updates the cached data in Valkey directly.
- [x] Change the `/store` endpoint so it writes to RustFS directly. It must not depend on the cron behavior.
- [x] Add custom Prometheus metrics. Examples: last successful refresh time, failed senseBox count, cache age, and store age.
- [x] Change `/readyz` to check these conditions:
  - [x] Half of the senseBoxes, plus one, are reachable.
  - [x] Cached data is no older than two cycles.
  - [x] Stored data is no older than two cycles.
- [x] Confirm the status thresholds (**decide**). The current rules leave gaps between 10 and 11 and between 36 and 37.
- [x] Confirm that `/version`, `/temperature`, and `/metrics` return the values the spec requires.
- [ ] Use Conventional Commits for all new commits. Add a commit message check in CI if you want enforcement.

## E. Tests

- [x] Remove `tests/weather.json`. Build the test data in code instead.
- [x] Control the current time in tests. Done without freezegun: the tests pass a fixed now, and they replace the clock in the app module.
- [x] Test `/version`.
- [ ] Test `/temperature` with a cache miss.
- [x] Test `/temperature` with a cache hit.
- [ ] Test `/temperature` with stale data.
- [ ] Test `/temperature` when all senseBoxes fail.
- [ ] Test `/temperature` when some senseBoxes fail.
- [x] Test the status value for each threshold range.
- [x] Test `/store`.
- [ ] Test `/cache`.
- [ ] Test `/readyz` in a healthy state and in each unhealthy state.
- [ ] Test `/metrics`.
- [ ] Test the Valkey error path.
- [ ] Test the RustFS error path.
- [ ] Mock Valkey and RustFS in unit tests.
- [ ] Add `pytest-cov` and set a minimum coverage value in CI.
- [ ] Write integration tests that use real Valkey and RustFS containers. Keep them in a separate folder such as `tests/integration/`.
- [ ] Mark integration tests so that they run in a separate CI job.
- [x] Add the README section that explains how to run each test type. The checklist item "documentation on how to test" requires this.

## F. Docker

- [ ] Pin the base image `python:3.12-alpine` to a digest.
- [ ] Confirm that the container runs as UID 65534 (`nobody`).
- [ ] Add a `HEALTHCHECK` or confirm that the Kubernetes probes replace it.
- [ ] Use `pip install --require-hashes` with a locked requirements file (optional, but recommended).
- [ ] Build the image locally with `docker build -t ddp:test --target prod .`.
- [ ] Run the image locally and call `/version`.
- [ ] Run Hadolint on the Dockerfile and fix all warnings.
- [ ] Enable Docker Content Trust for builds (`todo.txt` item 4).
- [ ] Use BuildKit secrets for any build-time credential (`todo.txt` item 5).
- [ ] Add Trivy image scanning to CI (`todo.txt` item 6).
- [ ] Add a build cache to the CI build step (`todo.txt` item 7).
- [ ] Add `docker-compose.yml` with the app, Valkey, and RustFS services. This avoids the root user for local runs (`todo.txt` item 24).

## G. Code quality and developer setup

- [ ] Run `black` on all Python files (`todo.txt` item 18).
- [x] Add a `.pylintrc` file if you need custom settings.
- [ ] Add the `.vscode/extensions.json` file with the recommended extensions (`todo.txt` item 19).
- [ ] Add a pre-commit configuration for black, pylint, and Hadolint (`todo.txt` item 17).
- [ ] Write the output of pylint and pytest as XML files and upload them as CI artifacts (`todo.txt` item 8).
- [ ] Check the GitHub Security tab and resolve every alert (`todo.txt` item 15).
- [ ] Resolve every open review comment (`todo.txt` item 16).
- [ ] Review `notes.txt` and move anything useful to the README. Then delete the file.
- [ ] Delete `todo.txt` after every item is complete.

## H. GitHub Actions CI

- [ ] Add RustFS in CI
- [x] Add `permissions: contents: read` at the top of the workflow. Grant write permissions only to the jobs that need them.
- [ ] Add a `pull_request` trigger so that CI runs before merge.
- [x] Update `actions/setup-python` from `v3` to a current version.
- [ ] Pin every action to a full commit SHA. The Scorecard check "Pinned-Dependencies" requires this.
- [x] Remove the duplicate venv setup from the lint job, or use the venv for all commands.
- [ ] Remove the hardcoded MinIO or RustFS password from the workflow file.
- [ ] Add the integration test job (checklist item 4.4).
- [ ] Add SonarQube with the Quality Gate check, or Semgrep (checklist item 4.4). For SonarQube, you must set up a server or use SonarCloud (**decide**).
- [x] Add a step that checks the Dockerfile with Hadolint.
- [ ] Keep Terrascan and check that it passes.
- [ ] Add Trivy scanning to the build job.
- [ ] Make the build job run only on `main` or on version tags.
- [ ] Prevent the build job from overwriting an existing image tag. Version tags must be immutable.
- [ ] Fix the version-check job so it fails on a mismatch.
- [ ] Review the CI best practices list and check each item (checklist item 4.4).
- [ ] Add `.github/dependabot.yml` for `pip` and `github-actions`.
- [ ] Confirm that the Scorecard workflow runs and fix every issue it reports (checklist item 3.4).
- [ ] Add `SECURITY.md`.
- [ ] Configure branch protection on `main`. It must require pull requests and passing CI checks, and it must block direct pushes (`todo.txt` item "don't push directly to main").

## I. Kubernetes core manifests

- [ ] Create a KIND configuration file with ingress-nginx support (checklist item 4.3). Confirm that the file is committed.
- [ ] Create a local KIND cluster and install ingress-nginx.
- [ ] Replace the `Pod` in `k8s/deploy-app.yml` with a `Deployment`.
- [x] Update the image tag from `0.2.1` to the current version.
- [ ] Add `readinessProbe` for `/readyz`.
- [ ] Add `livenessProbe` for `/version`.
- [ ] Add environment variables for the endpoint, bucket, and object names.
- [ ] Read the RustFS keys from a Kubernetes Secret.
- [ ] Raise the memory limit. 64 Mi is too low for this stack.
- [ ] Add `capabilities: drop: ["ALL"]` to the container security context.
- [ ] Add `seccompProfile: RuntimeDefault`.
- [ ] Test whether `readOnlyRootFilesystem` works with waitress. Add writable volumes for any path that the app writes to.
- [ ] Add `ingressClassName: nginx` to the Ingress.
- [ ] Add the RustFS manifests.
- [ ] Add the Valkey manifests (Deployment, Service).
- [ ] Add `PersistentVolumeClaim` objects for stateful services.
- [ ] Run Terrascan on the Kubernetes folder and fix all findings.
- [ ] Review Kubernetes security best practices (checklist item 5.3).
- [ ] Add `NetworkPolicy` objects (optional, but recommended).

## J. Helm and Kustomize

- [ ] Create a Helm chart for the application (checklist item 5.3).
- [ ] Move all hardcoded values into `values.yaml`.
- [ ] Add a `values-dev.yaml` file.
- [ ] Run `helm lint` and `helm template` in CI.
- [ ] Create Kustomize manifests for the infrastructure resources, such as Valkey and RustFS (checklist item 5.3).
- [ ] Decide which tool to use for each layer. Helm for the app and Kustomize for the infrastructure is the usual pattern (**decide**).
- [ ] Run `kubectl kustomize` and check the output in CI.

## K. Infrastructure as Code

- [ ] Choose a cloud provider or a local emulator (**decide**). The README suggests the free tier of a cloud provider or a local emulator.
- [ ] Create the account and the project for the chosen provider.
- [ ] Choose Terraform or OpenTofu and use it consistently. The topics list includes OpenTofu, but the README checklist says Terraform (**decide**).
- [ ] Write the Terraform code to create the Kubernetes cluster.
- [ ] Configure a remote state backend.
- [ ] Add variables and outputs.
- [ ] Run `terraform fmt`, `terraform validate`, and a security scanner (such as tfsec or Checkov) in CI.
- [ ] Apply the Terraform code and confirm the cluster works.
- [ ] Add a README section that explains how to create the cluster.
- [ ] Decide whether to use OpenShift (`todo.txt` item 2). If you use it, add the steps for it. If not, delete the item.

## L. Observability

- [ ] Create a Grafana Cloud free account (checklist item 5.4).
- [ ] Choose a collector. Grafana Agent is deprecated, and Grafana Alloy is its successor. Use Alloy unless your course requires Grafana Agent (**decide**).
- [ ] Deploy the collector to the cluster.
- [ ] Configure the collector to send logs to Loki and metrics to Prometheus or Grafana Cloud.
- [ ] Deploy Prometheus, or configure the collector, so that it scrapes `/metrics`.
- [ ] Create a dashboard for the custom metrics.
- [ ] Add alert rules for the `/readyz` failure state (optional).

## M. End-to-end tests (Venom)

- [ ] Install Venom.
- [ ] Write a Venom test suite for these checks: `/version`, `/temperature`, `/store`, `/cache`, `/readyz`, and `/metrics`.
- [ ] Add a CI job that creates a KIND cluster.
- [ ] In the CI job, deploy the infrastructure and the application.
- [ ] Run the Venom suite against the deployed application.
- [ ] Delete the KIND cluster at the end of the job.
- [ ] Confirm that the job fails when a check fails.

## N. Continuous delivery

- [ ] Create a CD workflow (checklist items 4.5 and 5.6, and `todo.txt` item 21).
- [ ] Set the CD workflow to push a versioned image to GHCR. The workflow must run only on version tags.
- [ ] Create GitHub environments for dev, stage, and prod, if you use them.
- [ ] Add environment protection rules and required reviewers for production.
- [ ] Write the deploy step. It can use `kubectl`, Helm, or Argo CD (see section O).
- [ ] Define the release process. It must include a version bump in `src/version.py`, a Git tag, a release note, and a rollback procedure.
- [ ] Apply CD best practices (checklist item 5.6).
- [ ] Confirm that the rollback works.

## O. Phase 6: GitOps and production readiness

- [ ] Install Argo CD in the cluster.
- [ ] Create Argo CD application manifests for the app and the infrastructure.
- [ ] Confirm that Argo CD syncs the application from Git.
- [ ] Set up ExternalDNS. This requires a domain name and a DNS provider (**decide**).
- [ ] Set up Cert-Manager. Use the Let's Encrypt staging issuer first, then the production issuer.
- [ ] Confirm that the application is reachable over HTTPS on your domain.
- [ ] Enable Dependabot alerts and updates for all ecosystems (checklist item 6).
- [ ] Move the external services to the cluster. Use open-source options for the Grafana stack, and use OpenTofu or Terraform in a CI job rather than a hosted service (checklist item 6).
- [ ] Install Kyverno and write at least one policy (optional).
- [ ] Build Dev, Stage, and Prod clusters with Terraform and Kustomize (optional).
- [ ] Add TestKube for test execution (optional).
- [ ] Develop a Kubernetes Operator for the app (optional, and a large task).

## P. Security and Scorecard

- [ ] Remove the committed `.env` and rotate every credential it contained.
- [ ] Turn on GitHub secret scanning and push protection.
- [ ] Turn on CodeQL or Semgrep for code scanning.
- [ ] Confirm that the Scorecard score is acceptable. Fix each failed check.
- [ ] Require code review for all changes to `main`.
- [ ] Sign release artifacts if the Scorecard check "Signed-Releases" applies to your project (optional).
- [ ] Review the Token-Permissions check and set minimal permissions in every workflow.
- [ ] Review the Dangerous-Workflow check.

## Q. Documentation

- [ ] Write a README that covers these topics:
  - [ ] Project purpose.
  - [ ] Architecture diagram.
  - [ ] Endpoint list.
  - [ ] Environment variables.
  - [ ] Local run steps.
  - [ ] Test steps.
  - [ ] Cluster creation steps.
  - [ ] Deployment steps.
  - [ ] Rollback steps.
- [ ] Document each phase as a pull request description.
- [ ] Mark every item in the README checklist as complete, or explain why it is not complete.
- [ ] Delete `todo.txt` and `notes.txt` after you move their content.
- [ ] Delete `tests/weather.json` if it still exists.

## R. Release

- [ ] Set the final version in `src/version.py`. Use semantic versioning.
- [ ] Tag the release in Git.
- [ ] Confirm that the CD workflow publishes the final image.
- [ ] Deploy the final version to the target cluster.
- [ ] Run the Venom suite against the final deployment.
- [ ] Confirm that Grafana shows the metrics and logs.
- [ ] Record the final state in the README.

## Suggested order

1. Sections A, B, and C (remove MinIO, move the code, and fix the bugs).
2. Sections D and E (spec and tests).
3. Sections F, G, and H (Docker, code quality, and CI).
4. Sections I and J (Kubernetes and Helm).
5. Sections K and L (Terraform and observability).
6. Sections M and N (end-to-end tests and CD).
7. Sections O, P, Q, and R (Phase 6, security, documentation, and release).
