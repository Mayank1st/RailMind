async def test_home_route_responds(client):
    """The ASGI client harness can reach a pure (no-DB, no-auth) route."""
    response = await client.get("/")

    assert response.status_code == 200
    assert response.json()["Name"] == "RailMind-BE"


async def test_db_test_route_uses_test_database(client):
    """The get_db override routes a real query through the test database."""
    response = await client.get("/db-test")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "connected"
    assert body["result"] == 1
