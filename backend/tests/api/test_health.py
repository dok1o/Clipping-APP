"""GET /health contract tests."""


def test_health_ok(client) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"]
    assert set(body["checks"]) == {"db", "redis", "s3"}
    assert body["checks"]["db"] == "ok"  # sqlite engine (test env)
    # s3/redis depend on environment (moto active or not / redis running or not)
    assert body["checks"]["s3"] in {"ok", "skip"}
    assert body["checks"]["redis"] in {"ok", "skip"}


def test_cors_allows_frontend_origin(client) -> None:
    response = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
