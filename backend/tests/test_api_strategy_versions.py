from fastapi.testclient import TestClient

from app.main import create_app


def test_strategy_version_detail_only(clean_db):
    app = create_app()
    client = TestClient(app)

    response = client.get("/api/v1/strategy-versions/sv-direct-v1")
    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "sv-direct-v1"
    assert payload["workflow_type"] == "direct"

    missing = client.get("/api/v1/strategy-versions/no-such-strategy")
    assert missing.status_code == 404

    list_response = client.get("/api/v1/strategy-versions")
    assert list_response.status_code == 404
