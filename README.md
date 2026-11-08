# dynamic-devops-project
[![Dynamic DevOps Roadmap](https://devopshive.net/badges/dynamic-devops-roadmap.svg)](https://github.com/DevOpsHiveHQ/dynamic-devops-roadmap)

[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/bourbonbourbon/dynamic-devops-project/badge)](https://scorecard.dev/viewer/?uri=github.com/bourbonbourbon/dynamic-devops-project)

### Setup
1. .env file
```
PORT="8080"
HOST="0.0.0.0"
SENSEBOXES="5eba5fbad46fb8001b799786,5a77184229b729001a150c10,6448d061258367000707ec8b,5e5fc72957703e001b7b1f0a,5eb3d2ea9724e9001ce71aa9,5f70d5b9a98020001bbd2c89"
MURL="localhost:9000"
MAK="ROOTUSER"
MSK="CHANGEME123"
MBUCKET="avg-temp"
MOBJECT="avg-temp"
VKURL="localhost"
VKPORT="6379"
```
2. Build the docker file
3. docker run -p 8080:8080 imagename:tag

# Main Objectives
Here's the HiveBox project plan as a checklist:

**Phase 1: Kickoff**

*1.1 Kickoff*
- [x] Understand your role in this project and how you work with other teams (assume you are in a team and don't act like you are working alone!)
- [x] Brush up on your knowledge about Software Project management (Hint: What is agile project management?)
- [x] Decide which Agile methodology you will use, such as Scrum, Kanban, or Scrumban (Kanban is recommended for this project)
- [x] Avoid Scope Creep! Make it work, make it right, make it fast!
- [x] Don't forget! You are managers of one!

*1.2 Preparation*
- [x] Create GitHub account (if you don't have one), then fork HiveBox repository on GitHub and start from there
- [x] Create GitHub project board for this repository (use Kanban template)
- [ ] Each phase should be presented as a pull request against the main branch. Don't push directly to the main branch!
- [ ] Document as you go. Always assume that someone else will read your project at any phase
- [x] Get 3 senseBox IDs close to each other from the openSenseMap website (you can use 5eba5fbad46fb8001b799786, 5c21ff8f919bf8001adf2488, and 5ade1acf223bd80019a1011c). Just copy the IDs, you will need them in the next steps

**Phase 2: Initial Application**

*2.1 Tools*
- [x] Git
- [x] VS Code
- [x] Docker

*2.2 Code*
- [x] Implement the code requirements in your GitHub repository fork for the project (done in phase 1)
- [x] Use Semantic Versioning v0.0.1 as the initial version of the HiveBox app
- [x] Create a function that prints the current app version. It just needs to print the version and then exit

*2.3 Containers*
- [x] Create a Dockerfile for the project
- [x] Build the Docker image and run it locally

*2.4 Testing*
- [x] Locally, run the app container and ensure it returns the correct value
- [x] Ensure that documentation is provided on how to test the application

**Phase 3: Endpoints, Tests, and CI**

*3.1 Tools*
- [x] Hadolint and VS Code hadolint extension
- [x] Pylint and VS Code Pylint extension

*3.2 Code*
- [ ] Use Conventional Commits for Git commits
- [x] Familiarize yourself with openSenseMap API
- [x] Implement the code requirements (Hint: Flask Quickstart or FastAPI)
- [x] Write unit tests for all endpoints
- [x] `/version` endpoint: no parameters, returns the version of the deployed app
- [x] `/temperature` endpoint: no parameters, returns current average temperature based on all senseBox data, with data no older than 1 hour

*3.3 Containers*
- [x] Apply Best Practices for containers (Hint: Docker Best Practices)

*3.4 Continuous Integration*
- [x] Create a GitHub Actions workflow for CI
- [x] Add a step to lint code and Dockerfile
- [x] Add a step to build the Docker image
- [x] Add a step to run unit tests
- [ ] Set up OpenSSF Scorecard GitHub Action and fix any issues reported by it

*3.5 Testing*
- [x] In the CI pipeline, call the `/version` endpoint and ensure it returns the correct value

**Phase 4: Kubernetes, Metrics, and Integration Tests**

*4.1 Tools*
- [x] Kind
- [x] Kubectl

*4.2 Code*
- [x] Implement the code requirements
- [x] Write integration tests (Hint: 3 ways to test your API with Python)
- [x] senseBox should be configurable via env vars
- [x] `/metrics` endpoint: no parameters, returns default Prometheus metrics about the app
- [x] `/temperature` endpoint: add a "status" field based on the average temperature value
  - [x] Less than 10: Too Cold
  - [x] Between 11-36: Good
  - [x] More than 37: Too Hot

*4.3 Containers*
- [x] Create a KIND configuration to run with Ingress-Nginx
- [x] Create Kubernetes core manifests to deploy the application

*4.4 Continuous Integration*
- [ ] Run code integration tests
- [ ] Run SonarQube for code quality, security, and static analysis (Hint: Use SonarQube Quality Gate check action, also consider Semgrep)
- [x] Run Terrascan for Kubernetes manifest misconfigurations and vulnerabilities (Hint: Terrascan GitHub Action)
- [ ] Apply Best Practices for CI (Hint: Best practices when adopting continuous integration)

*4.5 Continuous Delivery*
- [x] Create a GitHub Actions workflow for CD
- [x] Release by pushing a versioned Docker image to a container registry (Hint: Use GitHub Container Registry)

**Phase 5: Caching, Storage, Helm, and IaC**

*5.1 Tools*
- [x] Kind
- [x] Kubectl

*5.2 Code*
- [ ] Implement the code requirements
- [ ] Add a caching layer using Valkey, with a 5-minute caching cycle that refreshes the cache with the latest data each cycle
- [ ] Add a storage layer using MinIO, with a 5-minute storage cycle that stores another copy of the data each cycle
- [ ] `/temperature` endpoint: read from cache unless stale, in which case refresh the cache first
- [ ] `/cache` endpoint: no parameters, updates cached data directly on Valkey (outside of the cycle)
- [ ] `/store` endpoint: no parameters, stores a new copy of the data directly on MinIO (outside of the cycle)
- [ ] `/metrics` endpoint: extend Prometheus metrics with custom metrics based on code logic
- [ ] `/readyz` endpoint: returns HTTP 200 unless:
  - [ ] 50% + 1 of the configured senseBoxes are not accessible
  - [ ] Cached content is older than 2 cycles
  - [ ] Stored content is older than 2 cycles

*5.3 Containers*
- [ ] Create a Helm chart for the application (Hint: Awesome Helm List)
- [ ] Create Kustomize manifests for infrastructure resources like KeyVal (Hint: Awesome Kustomize List)
- [ ] Review Kubernetes Security Best Practices (Hint: Kubernetes Security Best Practices with tips for the CKS exam)
- [ ] Configure the Kubernetes app manifest to use `/readyz` as a readiness probe

*5.4 Infrastructure as Code*
- [ ] Deploy Grafana Agent to collect logs and metrics (Hint: Create Grafana Cloud free account to use Loki and Grafana)
- [ ] Create a Kubernetes cluster using Terraform IaC (Hint: Use free tier from any cloud provider or use a local emulator such as Floci)

*5.5 Continuous Integration*
- [ ] Create End-to-End test (Hint: Venom, a declarative test suite)
- [ ] Run the KIND cluster, deploy the app and infrastructure, then run the End-to-End test

*5.6 Continuous Delivery*
- [ ] Apply Best Practices for CD

**Phase 6: Free-Style Enhancements**

*Highly recommended*
- [ ] Deploy the application in Declarative GitOps style using Argo CD
- [ ] Prepare for production by setting up DNS (ExternalDNS) and Certificates (Cert-Manager)
- [ ] Automate dependency updates with Dependabot
- [ ] Move all external services (like Grafana.com and Terraform Cloud) to the Kubernetes cluster using open-source solutions

*Extra suggestions*
- [ ] Set up Kyverno for Policy as Code
- [ ] Build multi-environment Kubernetes clusters (Dev, Stage, and Prod) with Terraform and Kustomize
- [ ] Use TestKube for better testing execution
- [ ] Develop a Kubernetes Operator to handle the app operations (Hint: Introduction to Kubernetes Operators)
