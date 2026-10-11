# RCA-001: Spike in failed order placements (HTTP 503)

> **Simulated incident.** Produced by `python scripts/simulate_incident.py failures`, which sets `fail_rate=0.4` through the `/chaos` endpoint. Numbers below come from an actual local run (100 requests).

| Field | Value |
|---|---|
| Severity | SEV-2 (customer-facing, order placement degraded) |
| Detection | Alert `HighHttp5xxRate` and `HighOrderFailureRate` |
| Impact | 42 of 100 order attempts returned 503; 58 succeeded |
| Duration | Length of the test run; cleared by resetting `/chaos` |
| Status | Resolved |

## Timeline (simulated)
| Step | Event |
|---|---|
| T+0 | Fault injected: 40% of `POST /orders` return 503 |
| T+1m | 5xx ratio exceeds 5% threshold, `HighHttp5xxRate` enters pending |
| T+2m | Alert fires; on-call opens the Grafana "Overview" dashboard |
| T+4m | "Failed orders by reason" panel shows 100% of failures tagged `chaos_injected`, none tagged `out_of_stock` or `unknown_sku` |
| T+6m | Application logs show `order creation failed: injected fault`; `/health` and database are fine, so the fault is inside the order path, not the platform |
| T+8m | Fault cleared; success rate returns to 100% |

## Evidence
- `orders_failed_total{reason="chaos_injected"} 42`
- `http_requests_total{path="/orders",status="503"} 42`
- `/health` returned 200 throughout, so a plain uptime check would not have caught this. This is why the alert is based on error ratio, not just `up`.

## Root cause
A fault in the order-creation path caused a fixed fraction of requests to fail with 503. In a real incident the equivalent causes would be a bad deploy, a failing downstream dependency (payments, inventory service) or connection pool exhaustion.

## What went well
- Failure reason labels on `orders_failed_total` narrowed the cause in minutes.
- Business-level metric (failed orders) and technical metric (5xx ratio) agreed.

## What went wrong / gaps
- Health endpoint only checks database connectivity, so it stayed green during a partial failure.
- No automatic rollback on error-rate regression after deploy.

## Action items
| Action | Type | Owner |
|---|---|---|
| Add post-deploy canary check on `POST /orders` success rate and auto-rollback in the Cloud Run deploy job | Prevent | DevOps |
| Add a synthetic order probe (place and cancel a test order every minute) | Detect | DevOps |
| Keep reason labels on every failure path; add one for dependency timeouts | Detect | Backend |
| Add a runbook link in the alert annotation | Respond | DevOps |
