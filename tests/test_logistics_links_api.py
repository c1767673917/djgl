"""测试物流链接管理API (管理侧 /api/admin/logistics-links)"""
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core import delivery_sync_service as dss
from app.core.database import get_db_connection, init_database

TOKEN_A = "testtoken_links_aaa"
TOKEN_B = "testtoken_links_bbb"


@pytest.fixture
def test_client():
    return TestClient(app)


@pytest.fixture
def setup_links_data():
    """两家测试物流: A有2张快照(其中1张已上传), B无快照"""
    init_database()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO logistics_tokens (logistics_name, token, enabled, created_at, updated_at)"
            " VALUES ('测试物流甲', ?, 1, datetime('now'), datetime('now'))", (TOKEN_A,))
        cursor.execute(
            "INSERT INTO logistics_tokens (logistics_name, token, enabled, created_at, updated_at)"
            " VALUES ('测试物流乙', ?, 1, datetime('now'), datetime('now'))", (TOKEN_B,))

        snapshot_rows = [
            ("TESTLK1", "TESTLKCODE1", "客户甲", "2026-06-01", "测试物流甲", 500.0),
            ("TESTLK2", "TESTLKCODE2", "客户乙", "2026-06-02", "测试物流甲", 300.0),
        ]
        cursor.executemany(
            "INSERT INTO delivery_snapshot (delivery_id, delivery_code, customer_name,"
            " vouchdate, logistics_name, freight, synced_at)"
            " VALUES (?,?,?,?,?,?, datetime('now'))", snapshot_rows)

        # TESTLK1 已有上传记录(按business_id匹配) -> 待上传只剩TESTLK2
        cursor.execute(
            "INSERT INTO upload_history (business_id, file_name, file_size, upload_time, status)"
            " VALUES ('TESTLK1', 'test.jpg', 1024, datetime('now'), 'success')")
        conn.commit()

    yield

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM logistics_tokens WHERE logistics_name LIKE '测试物流%'")
        cursor.execute("DELETE FROM delivery_snapshot WHERE delivery_id LIKE 'TESTLK%'")
        cursor.execute("DELETE FROM upload_history WHERE business_id LIKE 'TESTLK%'")
        conn.commit()


class TestListLinks:

    def test_list_links_with_pending_count(self, test_client, setup_links_data):
        response = test_client.get("/api/admin/logistics-links/")
        assert response.status_code == 200
        data = response.json()

        links = {l["logistics_name"]: l for l in data["links"]}
        assert "测试物流甲" in links
        assert "测试物流乙" in links

        link_a = links["测试物流甲"]
        assert link_a["pending_count"] == 1  # TESTLK1已上传, 仅TESTLK2待传
        assert link_a["token"] == TOKEN_A
        assert link_a["link_path"] == f"/l/{TOKEN_A}"
        assert links["测试物流乙"]["pending_count"] == 0


class TestRegenerate:

    def test_regenerate_invalidates_old_token(self, test_client, setup_links_data):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id FROM logistics_tokens WHERE token = ?", (TOKEN_A,))
            link_id = cursor.fetchone()["id"]

        # 旧token门户可访问
        assert test_client.get(f"/api/portal/{TOKEN_A}/deliveries").status_code == 200

        response = test_client.post(f"/api/admin/logistics-links/{link_id}/regenerate")
        assert response.status_code == 200
        new_token = response.json()["token"]
        assert new_token != TOKEN_A

        # 旧token立即失效, 新token可用
        assert test_client.get(f"/api/portal/{TOKEN_A}/deliveries").status_code == 404
        assert test_client.get(f"/api/portal/{new_token}/deliveries").status_code == 200

    def test_regenerate_unknown_id(self, test_client, setup_links_data):
        response = test_client.post("/api/admin/logistics-links/999999999/regenerate")
        assert response.status_code == 404


class TestManualSync:

    def test_sync_accepted(self, test_client, monkeypatch):
        monkeypatch.setattr(dss, "is_sync_running", lambda: False)
        monkeypatch.setattr(dss, "get_manual_cooldown_remaining", lambda: 0)
        mock_sync = AsyncMock(return_value={"success": True})
        monkeypatch.setattr(dss, "sync_delivery_snapshot", mock_sync)

        response = test_client.post("/api/admin/logistics-links/sync")
        assert response.status_code == 202
        assert response.json() == {"started": True}

    def test_sync_conflict_when_running(self, test_client, monkeypatch):
        monkeypatch.setattr(dss, "is_sync_running", lambda: True)
        response = test_client.post("/api/admin/logistics-links/sync")
        assert response.status_code == 409

    def test_sync_conflict_in_cooldown(self, test_client, monkeypatch):
        monkeypatch.setattr(dss, "is_sync_running", lambda: False)
        monkeypatch.setattr(dss, "get_manual_cooldown_remaining", lambda: 120)
        response = test_client.post("/api/admin/logistics-links/sync")
        assert response.status_code == 409
        assert "120" in response.json()["detail"]

    def test_sync_status(self, test_client):
        init_database()
        response = test_client.get("/api/admin/logistics-links/sync-status")
        assert response.status_code == 200
        data = response.json()
        assert "running" in data
        assert "last_sync_at" in data
        assert "record_count" in data
