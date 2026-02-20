import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from rosie.api.main import app

client = TestClient(app)


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_list_models():
    resp = client.get("/v1/models")
    assert resp.status_code == 200
    data = resp.json()
    assert data["object"] == "list"
    assert len(data["data"]) >= 1


def test_chat_completions_no_message():
    resp = client.post("/v1/chat/completions", json={"model": "rosie", "messages": []})
    assert resp.status_code == 400


def test_chat_completions():
    with patch("rosie.api.main.ask", return_value="You have 5 EC2 instances.") as mock_ask:
        resp = client.post(
            "/v1/chat/completions",
            json={"model": "rosie", "messages": [{"role": "user", "content": "How many EC2 instances?"}]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["choices"][0]["message"]["content"] == "You have 5 EC2 instances."
        mock_ask.assert_called_once_with("How many EC2 instances?")


def test_inventory_empty():
    with patch("rosie.api.main.load_cache", return_value=[]):
        resp = client.get("/inventory")
        assert resp.status_code == 200
        assert resp.json()["count"] == 0


def test_collect_endpoint():
    with patch("rosie.api.main.run_all", return_value=[{"resource_id": "i-1234", "resource_type": "ec2:instance"}]) as mock_run, \
         patch("rosie.api.main.save_cache", return_value="/tmp/cache.json") as mock_save:
        resp = client.post("/collect", json={"region": "us-east-1", "account_id": "123456789012"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["collected"] == 1
