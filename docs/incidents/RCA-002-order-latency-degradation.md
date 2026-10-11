# RCA-002: Order endpoint latency degradation

> **Simulated incident.** Produced by `python scripts/simulate_incident.py latency`, which adds 800 ms to every `/orders` request. Numbers come from an actual local run (40 requests).

| Field | Value |
|---|---|
| Severity | SEV-3 (slow but successful orders) |
| Detection | Alert `SlowOrderRequests` (p95 of `POST /orders` above 1s for 2m) and Grafana latency panel |
| Impact | All 40 requests succeeded but with client-side p50 of 815 ms and p95 of 822 ms, versus a baseline p50 of 13 ms and p95 of 18 ms (roughly 45x slower) |
| Status | Resolved |

## Timeline (simulated)
| Step | Event |
|---|---|
| T+0 | Latency fault injected (+800 ms) |
| T+1m | p95 panel climbs from under 20 ms to about 0.8 s |
| T+3m | Note: 800 ms is below the 1 s alert threshold, so this specific fault would **not** page. The panel shows it, the alert does not |
| T+5m | On-call checks request-rate panel: traffic is unchanged, so this is not a load problem |
| T+7m | Error ratio is 0%, so the service is healthy but slow; inspection points to a slow dependency or database rather than application errors |
| T+9m | Fault cleared; latency returns to baseline |

## Root cause
Added processing delay on the order path. Real-world equivalents: slow queries from a missing index, database CPU saturation, cold starts on Cloud Run (`min_instance_count = 0`), or a slow downstream call.

## Key finding
The alert threshold (1 s) is looser than the user experience target. An 800 ms checkout API call degrades the customer experience yet would never page anyone.

## Action items
| Action | Type | Owner |
|---|---|---|
| Define an SLO (for example, 95% of order requests under 500 ms over 28 days) and alert on burn rate instead of a single fixed threshold | Detect | DevOps |
| Set Cloud Run `min_instance_count = 1` in production to remove cold-start latency | Prevent | DevOps |
| Add database query timing metric and slow-query logging | Detect | Backend |
| Load test in CI before release to catch regressions | Prevent | DevOps |
