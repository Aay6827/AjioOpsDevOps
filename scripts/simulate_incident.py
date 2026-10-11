"""Drive traffic against the order service and simulate incidents.

Usage:
    python scripts/simulate_incident.py baseline
    python scripts/simulate_incident.py failures   # 40% injected 503s on order creation
    python scripts/simulate_incident.py latency    # +800ms on /orders endpoints
    python scripts/simulate_incident.py stockout   # drain a SKU until orders are rejected

Each scenario sends traffic, prints a client-side summary, and resets fault
injection afterwards so the system returns to normal.
"""
import argparse
import random
import statistics
import time

import httpx

SKUS = ["AJ-TSHIRT-001", "AJ-JEANS-002", "AJ-KURTA-003", "AJ-SNEAKER-004"]


def place_order(client, sku=None, qty=1):
    sku = sku or random.choice(SKUS)
    start = time.perf_counter()
    r = client.post(
        "/orders",
        json={"customer_id": f"cust-{random.randint(1, 500)}", "items": [{"sku": sku, "quantity": qty}]},
    )
    return r.status_code, time.perf_counter() - start


def run_traffic(client, n, sku=None, qty=1, pause=0.0):
    codes, latencies = {}, []
    for _ in range(n):
        code, took = place_order(client, sku, qty)
        codes[code] = codes.get(code, 0) + 1
        latencies.append(took)
        if pause:
            time.sleep(pause)
    return codes, latencies


def summarise(name, codes, latencies):
    total = sum(codes.values())
    ok = codes.get(201, 0)
    lat = sorted(latencies)
    p95 = lat[int(0.95 * (len(lat) - 1))]
    print(f"[{name}] requests={total} success={ok} ({ok / total:.0%}) status_codes={dict(sorted(codes.items()))}")
    print(f"[{name}] latency client-side: p50={statistics.median(lat) * 1000:.0f}ms p95={p95 * 1000:.0f}ms")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scenario", choices=["baseline", "failures", "latency", "stockout"])
    ap.add_argument("--base-url", default="http://localhost:18000")
    ap.add_argument("--requests", type=int, default=100)
    args = ap.parse_args()

    with httpx.Client(base_url=args.base_url, timeout=30) as c:
        # Top up stock so scenarios start from a known state.
        for sku in SKUS:
            c.post("/inventory/restock", json={"sku": sku, "quantity": 500})

        if args.scenario == "baseline":
            summarise("baseline", *run_traffic(c, args.requests))

        elif args.scenario == "failures":
            c.post("/chaos", json={"fail_rate": 0.4, "latency_ms": 0})
            print("fault injected: fail_rate=0.4")
            try:
                summarise("failures", *run_traffic(c, args.requests))
            finally:
                c.post("/chaos", json={"fail_rate": 0.0, "latency_ms": 0})
                print("fault cleared")

        elif args.scenario == "latency":
            c.post("/chaos", json={"fail_rate": 0.0, "latency_ms": 800})
            print("fault injected: latency_ms=800")
            try:
                summarise("latency", *run_traffic(c, min(args.requests, 40)))
            finally:
                c.post("/chaos", json={"fail_rate": 0.0, "latency_ms": 0})
                print("fault cleared")

        elif args.scenario == "stockout":
            # Jackets: seeded low. Buy 5 at a time until stock runs out.
            stock = next(p["stock"] for p in c.get("/inventory").json() if p["sku"] == "AJ-JACKET-005")
            print(f"jacket stock before: {stock}")
            summarise("stockout", *run_traffic(c, args.requests, sku="AJ-JACKET-005", qty=5))


if __name__ == "__main__":
    main()
