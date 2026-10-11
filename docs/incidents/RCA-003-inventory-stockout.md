# RCA-003: Order rejections caused by inventory stock-out

> **Simulated incident.** Produced by `python scripts/simulate_incident.py stockout`, which keeps ordering the Bomber Jacket (`AJ-JACKET-005`, seeded with 15 units) in lots of 5. Numbers come from an actual local run.

| Field | Value |
|---|---|
| Severity | SEV-3 (business impact, platform healthy) |
| Detection | Gauge `low_stock_skus` greater than 0 (alert `LowStockSKUs`), then rising `orders_failed_total{reason="out_of_stock"}` |
| Impact | 7 of 10 order attempts rejected with HTTP 409; only 3 orders (15 units) fulfilled |
| Status | Resolved by restocking |

## Timeline (simulated)
| Step | Event |
|---|---|
| T+0 | Jacket stock at 15 (above the reorder threshold of 10); demand spike begins |
| T+1m | Stock falls under the reorder threshold (10); `low_stock_skus` becomes 1 |
| T+6m | `LowStockSKUs` fires (info level) after its 5-minute hold |
| T+7m | `HighOrderFailureRate` fires: failures are all `out_of_stock` |
| T+10m | `POST /inventory/restock` adds units; order success recovers |

## Root cause
Demand exceeded available stock and no reorder was triggered when stock first crossed the threshold. This is a supply-chain process gap and not a software fault, and the application behaved correctly: stock was never oversold and rejected orders did not decrement inventory (covered by `test_out_of_stock_rejected_and_stock_untouched`).

## Why this matters for DevOps
Telling an infrastructure failure apart from a business-logic rejection is the first triage decision. The `reason` label on `orders_failed_total` makes that distinction visible immediately: 409 `out_of_stock` means page purchasing, whereas 503 means page engineering.

## Action items
| Action | Type | Owner |
|---|---|---|
| Route `LowStockSKUs` to the purchasing team's channel, not engineering | Respond | DevOps |
| Make the reorder threshold per-SKU, based on sales velocity | Prevent | Backend |
| Exclude `out_of_stock` rejections from the engineering error-rate alert, or alert on them separately | Detect | DevOps |
