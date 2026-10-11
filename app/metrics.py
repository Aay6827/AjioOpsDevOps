from prometheus_client import Counter, Gauge, Histogram

HTTP_REQUESTS = Counter(
    "http_requests_total", "HTTP requests", ["method", "path", "status"]
)
HTTP_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "path"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)
ORDERS_PLACED = Counter("orders_placed_total", "Orders successfully placed")
ORDERS_FAILED = Counter("orders_failed_total", "Orders that failed", ["reason"])
ORDER_STATUS_TRANSITIONS = Counter(
    "order_status_transitions_total", "Order status changes", ["to_status"]
)
SHIPMENTS_CREATED = Counter(
    "shipments_created_total", "Shipments created", ["carrier"]
)
LOW_STOCK_SKUS = Gauge("low_stock_skus", "Number of SKUs below the reorder threshold")
