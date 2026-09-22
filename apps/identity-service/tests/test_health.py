def test_health(client):
    assert client.get("/healthz").json()["status"] == "ok"
