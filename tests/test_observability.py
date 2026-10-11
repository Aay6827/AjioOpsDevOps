def metric_value(text, name_with_labels):
    for line in text.splitlines():
        if line.startswith(name_with_labels + " "):
            return float(line.split()[-1])
    return 0.0


def test_metrics_endpoint_exposes_app_metrics(client):
    client.post("/orders", json={"customer_id": "c", "items": [{"sku": "AJ-TSHIRT-001", "quantity": 1}]})
    text = client.get("/metrics").text
    assert "orders_placed_total" in text
    assert "http_request_duration_seconds_bucket" in text
    assert metric_value(text, "orders_placed_total") >= 1


def test_failed_orders_counted_by_reason(client):
    before = metric_value(client.get("/metrics").text, 'orders_failed_total{reason="unknown_sku"}')
    client.post("/orders", json={"customer_id": "c", "items": [{"sku": "NOPE", "quantity": 1}]})
    after = metric_value(client.get("/metrics").text, 'orders_failed_total{reason="unknown_sku"}')
    assert after == before + 1


def test_chaos_failure_injection(client):
    assert client.post("/chaos", json={"fail_rate": 1.0, "latency_ms": 0}).status_code == 200
    r = client.post("/orders", json={"customer_id": "c", "items": [{"sku": "AJ-TSHIRT-001", "quantity": 1}]})
    assert r.status_code == 503
    text = client.get("/metrics").text
    assert metric_value(text, 'orders_failed_total{reason="chaos_injected"}') >= 1
    # reset and confirm recovery
    client.post("/chaos", json={"fail_rate": 0.0, "latency_ms": 0})
    r = client.post("/orders", json={"customer_id": "c", "items": [{"sku": "AJ-TSHIRT-001", "quantity": 1}]})
    assert r.status_code == 201


def test_low_stock_gauge(client):
    # Bomber jacket seeded at 15 (threshold 10). Buying 6 drops it to 9.
    client.post("/orders", json={"customer_id": "c", "items": [{"sku": "AJ-JACKET-005", "quantity": 6}]})
    assert metric_value(client.get("/metrics").text, "low_stock_skus") == 1.0
