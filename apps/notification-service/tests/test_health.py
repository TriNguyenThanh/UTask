def test_health(client):
    assert client.get("/healthz").json()["service"] == "notification-service"
