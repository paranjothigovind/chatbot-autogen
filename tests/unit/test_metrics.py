from app.core.metrics import Metrics


def test_metrics_record_without_error() -> None:
    m = Metrics()
    m.record_request("/x", "GET", 200, 1.5)
    m.record_request("/x", "GET", 503, 2.5)
    m.record_usage("user-a", 10, 5, 0.001)
