"""测试物流待上传门户API (物流侧 /api/portal 与页面 /l/{token})"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import get_db_connection, init_database

TOKEN_A = "testtoken_portal_aaa"
TOKEN_B = "testtoken_portal_bbb"
TOKEN_DISABLED = "testtoken_portal_off"


@pytest.fixture
def test_client():
    return TestClient(app)


@pytest.fixture
def setup_portal_data():
    """
    测试数据:
      测试物流甲(TOKEN_A): 6张快照
        - TESTPT1: 无上传记录 -> 待上传
        - TESTPT2: 有success记录(business_id匹配) -> 排除
        - TESTPT3: 有failed记录(doc_number匹配) -> 排除(不限status)
        - TESTPT4: 有记录但已软删除 -> 重新出现为待上传
        - TESTPT6: 仅有仓库(upload_type='仓库')同号记录 -> 不排除, 仍待上传
        - TESTPT7: 有upload_type为空串的历史记录 -> 按"物流"对待, 排除
      测试物流乙(TOKEN_B): 1张快照 TESTPT5
      测试物流丙(TOKEN_DISABLED): 已禁用
    """
    init_database()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.executemany(
            "INSERT INTO logistics_tokens (logistics_name, token, enabled, created_at, updated_at)"
            " VALUES (?, ?, ?, datetime('now'), datetime('now'))",
            [
                ("测试物流甲", TOKEN_A, 1),
                ("测试物流乙", TOKEN_B, 1),
                ("测试物流丙", TOKEN_DISABLED, 0),
            ])

        cursor.executemany(
            "INSERT INTO delivery_snapshot (delivery_id, delivery_code, customer_name,"
            " vouchdate, logistics_name, freight, synced_at)"
            " VALUES (?,?,?,?,?,?, datetime('now'))",
            [
                ("TESTPT1", "TESTPTCODE1", "客户甲", "2026-06-03", "测试物流甲", 500.0),
                ("TESTPT2", "TESTPTCODE2", "客户乙", "2026-06-01", "测试物流甲", 300.0),
                ("TESTPT3", "TESTPTCODE3", "客户丙", "2026-06-02", "测试物流甲", 700.0),
                ("TESTPT4", "TESTPTCODE4", "客户丁", "2026-06-04", "测试物流甲", 200.0),
                ("TESTPT5", "TESTPTCODE5", "客户戊", "2026-06-05", "测试物流乙", 900.0),
                ("TESTPT6", "TESTPTCODE6", "客户己", "2026-06-06", "测试物流甲", 400.0),
                ("TESTPT7", "TESTPTCODE7", "客户庚", "2026-06-07", "测试物流甲", 600.0),
            ])

        cursor.executemany(
            "INSERT INTO upload_history (business_id, doc_number, file_name, file_size,"
            " upload_time, status, deleted_at, upload_type)"
            " VALUES (?, ?, 'test.jpg', 1024, datetime('now'), ?, ?, ?)",
            [
                ("TESTPT2", None, "success", None, "物流"),        # business_id 匹配排除
                ("OTHERID", "TESTPTCODE3", "failed", None, "物流"),  # doc_number 匹配排除(failed也算)
                ("TESTPT4", "TESTPTCODE4", "success", "2026-06-10 10:00:00", "物流"),  # 已软删除
                ("TESTPT6", "TESTPTCODE6", "success", None, "仓库"),  # 仓库同号, 不排除物流回单
                ("TESTPT7", "TESTPTCODE7", "success", None, ""),      # 空串按"物流"对待, 排除
            ])

        # 记录同步时间元数据, 供 last_sync_at 断言
        cursor.execute(
            "INSERT INTO app_meta (key, value) VALUES ('delivery_sync_last_at', '2026-07-03T10:00:00')"
            " ON CONFLICT(key) DO UPDATE SET value = excluded.value")
        conn.commit()

    yield

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM logistics_tokens WHERE logistics_name LIKE '测试物流%'")
        cursor.execute("DELETE FROM delivery_snapshot WHERE delivery_id LIKE 'TESTPT%'")
        cursor.execute(
            "DELETE FROM upload_history WHERE business_id LIKE 'TESTPT%'"
            " OR doc_number LIKE 'TESTPTCODE%'")
        conn.commit()


class TestPortalDeliveries:

    def test_only_own_company_and_exclusion(self, test_client, setup_portal_data):
        response = test_client.get(f"/api/portal/{TOKEN_A}/deliveries")
        assert response.status_code == 200
        data = response.json()

        assert data["logistics_name"] == "测试物流甲"
        assert data["last_sync_at"] == "2026-07-03T10:00:00"

        codes = [d["delivery_code"] for d in data["deliveries"]]
        # TESTPT2(business_id匹配)与TESTPT3(doc_number匹配,failed也算)被排除;
        # TESTPT4的记录已软删除 -> 重新出现; 不含其他公司的TESTPT5;
        # TESTPT6仅有仓库同号记录 -> 仍待上传; TESTPT7空串upload_type按物流 -> 排除
        assert codes == ["TESTPTCODE1", "TESTPTCODE4", "TESTPTCODE6"]  # 按vouchdate升序
        assert data["total"] == 3

    def test_warehouse_upload_does_not_exclude(self, test_client, setup_portal_data):
        """仓库上传(upload_type='仓库')同号记录不代表物流回单已传, 不应排除"""
        response = test_client.get(f"/api/portal/{TOKEN_A}/deliveries")
        codes = [d["delivery_code"] for d in response.json()["deliveries"]]
        assert "TESTPTCODE6" in codes

    def test_legacy_empty_upload_type_excludes(self, test_client, setup_portal_data):
        """历史记录upload_type为空串时按默认'物流'对待, 正常排除"""
        response = test_client.get(f"/api/portal/{TOKEN_A}/deliveries")
        codes = [d["delivery_code"] for d in response.json()["deliveries"]]
        assert "TESTPTCODE7" not in codes

    def test_upload_url_format(self, test_client, setup_portal_data):
        response = test_client.get(f"/api/portal/{TOKEN_A}/deliveries")
        delivery = response.json()["deliveries"][0]
        assert delivery["delivery_id"] == "TESTPT1"
        assert delivery["upload_url"] == (
            "/?business_id=TESTPT1&doc_number=TESTPTCODE1"
            "&doc_type=%E9%94%80%E5%94%AE"  # "销售" URL编码
        )

    def test_other_company_isolated(self, test_client, setup_portal_data):
        response = test_client.get(f"/api/portal/{TOKEN_B}/deliveries")
        assert response.status_code == 200
        data = response.json()
        assert data["logistics_name"] == "测试物流乙"
        assert [d["delivery_id"] for d in data["deliveries"]] == ["TESTPT5"]

    def test_invalid_token_404(self, test_client, setup_portal_data):
        assert test_client.get("/api/portal/nonexistent_token/deliveries").status_code == 404

    def test_disabled_token_404(self, test_client, setup_portal_data):
        assert test_client.get(f"/api/portal/{TOKEN_DISABLED}/deliveries").status_code == 404

    def test_access_updates_last_access_at(self, test_client, setup_portal_data):
        test_client.get(f"/api/portal/{TOKEN_A}/deliveries")
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT last_access_at FROM logistics_tokens WHERE token = ?", (TOKEN_A,))
            assert cursor.fetchone()["last_access_at"] is not None


class TestPortalPage:

    def test_valid_token_serves_page(self, test_client, setup_portal_data):
        response = test_client.get(f"/l/{TOKEN_A}")
        assert response.status_code == 200
        assert "logistics-portal" in response.text

    def test_invalid_token_page_404(self, test_client, setup_portal_data):
        assert test_client.get("/l/nonexistent_token").status_code == 404

    def test_disabled_token_page_404(self, test_client, setup_portal_data):
        assert test_client.get(f"/l/{TOKEN_DISABLED}").status_code == 404
