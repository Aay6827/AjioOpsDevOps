![CI](https://github.com/Aay6827/AjioOpsDevOps/actions/workflows/ci-cd.yml/badge.svg)


# AjioOpsDevOps

DevOps automation and cloud-native monitoring for an Ajio-style e-commerce order management and supply chain platform. Target role: **Junior DevOps Engineer**.

A FastAPI service handles the journey from order placement to inventory reservation, warehouse processing, shipment assignment and delivery tracking. Around it sit a CI/CD pipeline, containers, Terraform for GCP, Prometheus/Grafana monitoring, alert rules and incident write-ups.

## Architecture

```
 Developer ──push──> GitHub ──> GitHub Actions
                                  │ 1. pytest (SQLite) + smoke test (Postgres service)
                                  │ 2. terraform fmt / validate
                                  │ 3. docker build -> Artifact Registry
                                  └ 4. deploy -> Cloud Run -> post-deploy /health check

 Customer ──> Cloud Run (FastAPI) ──> Cloud SQL (PostgreSQL 16)
                  │  /metrics                 ▲ DATABASE_URL from Secret Manager
                  ▼
             Prometheus ──> alert rules      Grafana dashboard
```

| Area | Tools | Where |
|---|---|---|
| Application | Python, FastAPI, SQLAlchemy, PostgreSQL | `app/` |
| Testing | Pytest, API tests via TestClient | `tests/` |
| CI/CD | GitHub Actions | `.github/workflows/ci-cd.yml` |
| Containers | Docker, Docker Compose | `Dockerfile`, `docker-compose.yml` |
| Cloud + IaC | GCP (Cloud Run, Cloud SQL, Artifact Registry, Secret Manager), Terraform | `terraform/` |
| Monitoring | Prometheus, Grafana | `monitoring/` |
| Incident response | Fault injection, alerts, RCAs | `scripts/`, `docs/incidents/` |

## Run it locally

```bash
# 1. Unit + API tests
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pytest -q

# 2. Full stack: API + PostgreSQL + Prometheus + Grafana
docker compose up --build
```

| Service | URL |
|---|---|
| API docs (Swagger) | http://localhost:18000/docs |
| Metrics | http://localhost:18000/metrics |
| Prometheus + alerts | http://localhost:19090 |
| Grafana (admin / admin) | http://localhost:13000 (dashboard: "Ajio Order Service - Overview") |

## API at a glance

| Endpoint | Purpose |
|---|---|
| `POST /orders` | Place an order; validates and reserves stock atomically |
| `GET /orders/{id}` | Order with items and shipment |
| `PATCH /orders/{id}/status` | PLACED → CONFIRMED → PACKED (or CANCELLED, which returns stock) |
| `POST /orders/{id}/ship` | Assign carrier and tracking number (order must be PACKED) |
| `POST /shipments/{tracking}/advance` | Move shipment through pickup → transit → delivered |
| `GET /shipments/{tracking}` | Delivery tracking |
| `GET /inventory`, `POST /inventory/restock` | Stock levels |
| `GET /health`, `GET /metrics` | Liveness (checks DB) and Prometheus metrics |
| `POST /chaos` | Fault injection for incident simulations |

## Monitoring

Metrics exposed: request count and latency histogram by route and status, orders placed, failed orders by reason (`out_of_stock`, `unknown_sku`, `chaos_injected`), order status transitions, shipments by carrier, and low-stock SKU count.

Alerts (`monitoring/alerts.yml`): `OrderServiceDown`, `HighHttp5xxRate`, `HighOrderFailureRate`, `SlowOrderRequests`, `LowStockSKUs`.

## Incident simulations

With the stack running:

```bash
pip install httpx
python scripts/simulate_incident.py baseline
python scripts/simulate_incident.py failures    # 40% of order requests return 503
python scripts/simulate_incident.py latency     # +800 ms on order endpoints
python scripts/simulate_incident.py stockout    # drain a SKU, orders rejected with 409
```

Watch the Grafana dashboard and Prometheus Alerts page while each runs. Written root-cause analyses, based on real runs of these scenarios, are in `docs/incidents/`.

## Deploying to GCP

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars   # set project_id and db_password
terraform init && terraform plan && terraform apply
```

For CI, set these GitHub repository secrets: `GCP_PROJECT_ID`, `GCP_WORKLOAD_IDENTITY_PROVIDER`, `GCP_SERVICE_ACCOUNT` (keyless auth via Workload Identity Federation; no long-lived keys). Cloud Run scales to zero and is capped at 3 instances to keep demo costs low. Run `terraform destroy` when finished.

## Status of verification

- Verified: 18 pytest tests pass; app run locally and all four incident scenarios executed; YAML and Grafana JSON parse.
- Not verified in the build environment: `docker compose up`, `terraform validate/apply`, and the GitHub Actions run. Run these on your machine first and fix any version-specific issues before presenting.

## Ideas to extend
- Add Prometheus Alertmanager with Slack or email routing
- Add Cloud Monitoring alert policies in Terraform
- Add canary or blue/green rollout with automatic rollback
- Add load testing (k6 or Locust) as a CI stage


