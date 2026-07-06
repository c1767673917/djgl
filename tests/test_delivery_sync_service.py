"""测试发货单快照同步服务 (delivery_sync_service)"""
import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest

from app.core import delivery_sync_service as dss
from app.core.database import get_db_connection, init_database


# ========== 工具 ==========

def make_record(delivery_id, code=None, logistics="测试物流公司A", freight="500",
                customer="客户甲", vouchdate="2026-06-01 00:00:00",
                shipping_memo="测试发货备注", total_price_qty=100.0):
    """构造发货列表原始记录(表头行)"""
    return {
        "id": delivery_id,
        "code": code or f"TESTCODE-{delivery_id}",
        "agentId_name": customer,
        "vouchdate": vouchdate,
        "shippingMemo": shipping_memo,
        "totalOutStockPriceQty": total_price_qty,
        "deliveryVoucherDefineCharacter": {
            "RX003_name": logistics,
            "RX004": freight,
        },
    }


def make_page(records, page_count=1, record_count=None):
    """构造 get_delivery_list 的成功返回"""
    return {
        "success": True,
        "record_count": record_count if record_count is not None else len(records),
        "page_count": page_count,
        "records": records,
        "error_code": None,
        "error_message": None,
    }


def make_failed_page(error_code="NETWORK_ERROR", error_message="连接超时"):
    return {
        "success": False,
        "record_count": 0,
        "page_count": 0,
        "records": [],
        "error_code": error_code,
        "error_message": error_message,
    }


def query_snapshot_ids():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT delivery_id FROM delivery_snapshot ORDER BY delivery_id")
        return [row["delivery_id"] for row in cursor.fetchall()]


# ========== fixtures ==========

@pytest.fixture
def preserve_tables(monkeypatch):
    """确保新表存在; 备份并在测试后还原快照/元数据, 清理测试token; 加速重试与节流"""
    init_database()

    with get_db_connection() as conn:
        cursor = conn.cursor()
        snapshot_backup = [tuple(row) for row in cursor.execute(
            "SELECT delivery_id, delivery_code, customer_name, vouchdate,"
            " logistics_name, freight, shipping_memo, total_price_qty, synced_at"
            " FROM delivery_snapshot"
        ).fetchall()]
        meta_backup = [tuple(row) for row in cursor.execute(
            "SELECT key, value FROM app_meta"
        ).fetchall()]

    # 测试提速: 去掉页间隔与重试等待
    monkeypatch.setattr(dss, "_PAGE_RETRY_DELAYS", [0, 0])
    monkeypatch.setattr(dss.settings, "DELIVERY_SYNC_PAGE_INTERVAL_SECONDS", 0.0)
    # 重置手动冷却
    monkeypatch.setattr(dss, "_last_manual_sync_ts", 0.0)

    yield

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM delivery_snapshot")
        cursor.executemany(
            "INSERT INTO delivery_snapshot (delivery_id, delivery_code, customer_name,"
            " vouchdate, logistics_name, freight, shipping_memo, total_price_qty,"
            " synced_at) VALUES (?,?,?,?,?,?,?,?,?)",
            snapshot_backup,
        )
        cursor.execute("DELETE FROM app_meta")
        cursor.executemany(
            "INSERT INTO app_meta (key, value) VALUES (?,?)", meta_backup
        )
        cursor.execute("DELETE FROM logistics_tokens WHERE logistics_name LIKE '测试物流%'")
        conn.commit()


def patch_delivery_list(side_effect):
    """patch 同步服务中 YonYouClient.get_delivery_list"""
    return patch.object(
        dss.YonYouClient, "get_delivery_list",
        new_callable=AsyncMock, side_effect=side_effect,
    )


# ========== 本地过滤规则 ==========

class TestExtractAndFilter:

    def test_self_pickup_excluded(self):
        records = [
            make_record("1", logistics="自提Pick Up", freight="500"),
            make_record("2", logistics="自提", freight="500"),
            make_record("3", logistics="测试物流公司A", freight="500"),
        ]
        kept = dss._extract_and_filter(records)
        assert [r["delivery_id"] for r in kept] == ["3"]

    def test_freight_threshold(self):
        records = [
            make_record("1", freight="100"),     # 等于阈值, 不保留
            make_record("2", freight="100.01"),  # 大于阈值, 保留
            make_record("3", freight="0"),
            make_record("4", freight=""),
            make_record("5", freight="abc"),
            make_record("6", freight=None),
            make_record("7", freight="1,100"),   # 带千分位逗号, 保留
            make_record("8", freight=730),       # 数值类型, 保留
        ]
        kept = dss._extract_and_filter(records)
        kept_ids = sorted(r["delivery_id"] for r in kept)
        assert kept_ids == ["2", "7", "8"]
        freight_map = {r["delivery_id"]: r["freight"] for r in kept}
        assert freight_map["7"] == 1100.0

    def test_missing_logistics_excluded(self):
        records = [
            make_record("1", logistics=None),
            make_record("2", logistics=""),
            make_record("3", logistics="  "),
        ]
        rec_no_dc = make_record("4")
        rec_no_dc["deliveryVoucherDefineCharacter"] = None
        records.append(rec_no_dc)
        assert dss._extract_and_filter(records) == []

    def test_dedup_by_delivery_id(self):
        records = [
            make_record("1", customer="第一次"),
            make_record("1", customer="第二次"),
        ]
        kept = dss._extract_and_filter(records)
        assert len(kept) == 1

    def test_field_extraction(self):
        rec = make_record(2574858235647885313, code="RXXOUT202607-0093",
                          customer="京东-营多捞面旗舰店",
                          vouchdate="2026-06-30 00:00:00", freight="730",
                          shipping_memo="22026.5月平台开票", total_price_qty=1430.0)
        kept = dss._extract_and_filter([rec])
        assert kept == [{
            "delivery_id": "2574858235647885313",  # 长整型id转为字符串
            "delivery_code": "RXXOUT202607-0093",
            "customer_name": "京东-营多捞面旗舰店",
            "vouchdate": "2026-06-30",
            "logistics_name": "测试物流公司A",
            "freight": 730.0,
            "shipping_memo": "22026.5月平台开票",
            "total_price_qty": 1430.0,
        }]

    def test_memo_and_qty_missing_or_blank(self):
        """shippingMemo缺失/空白置None, totalOutStockPriceQty非法置None"""
        rec = make_record("1", shipping_memo="  ", total_price_qty=None)
        rec2 = make_record("2", shipping_memo=None, total_price_qty="abc")
        kept = {r["delivery_id"]: r for r in dss._extract_and_filter([rec, rec2])}
        assert kept["1"]["shipping_memo"] is None
        assert kept["1"]["total_price_qty"] is None
        assert kept["2"]["shipping_memo"] is None
        assert kept["2"]["total_price_qty"] is None


# ========== 同步主流程 ==========

class TestSyncDeliverySnapshot:

    @pytest.mark.asyncio
    async def test_multi_page_sync(self, preserve_tables):
        """按pageCount拉完多页并落库, 自动生成token"""
        pages = [
            make_page([make_record("TESTDS1")], page_count=3),
            make_page([make_record("TESTDS2", logistics="测试物流公司B")], page_count=3),
            make_page([make_record("TESTDS3")], page_count=3),
        ]
        with patch_delivery_list(pages) as mock_list:
            result = await dss.sync_delivery_snapshot(trigger="scheduled")

        assert result["success"] is True
        assert result["pages"] == 3
        assert result["kept_count"] == 3
        assert mock_list.call_count == 3
        assert query_snapshot_ids() == ["TESTDS1", "TESTDS2", "TESTDS3"]

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT shipping_memo, total_price_qty FROM delivery_snapshot"
                " WHERE delivery_id = 'TESTDS1'"
            )
            row = cursor.fetchone()
        assert row["shipping_memo"] == "测试发货备注"
        assert row["total_price_qty"] == 100.0

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT logistics_name, token FROM logistics_tokens "
                "WHERE logistics_name LIKE '测试物流%' ORDER BY logistics_name"
            )
            rows = cursor.fetchall()
        assert [row["logistics_name"] for row in rows] == ["测试物流公司A", "测试物流公司B"]
        assert all(len(row["token"]) >= 16 for row in rows)

        state = dss.get_sync_state()
        assert state["last_status"] == "success"
        assert state["record_count"] == 3

    @pytest.mark.asyncio
    async def test_empty_page_early_stop(self, preserve_tables):
        """中途空页提前终止(pageCount漂移防御)"""
        pages = [
            make_page([make_record("TESTDS1")], page_count=5),
            make_page([], page_count=5),
        ]
        with patch_delivery_list(pages) as mock_list:
            result = await dss.sync_delivery_snapshot()

        assert result["success"] is True
        assert mock_list.call_count == 2  # 第2页为空即停止, 不请求第3页
        assert query_snapshot_ids() == ["TESTDS1"]

    @pytest.mark.asyncio
    async def test_max_pages_cap(self, preserve_tables, monkeypatch):
        """pageCount超过MAX_PAGES时截断"""
        monkeypatch.setattr(dss.settings, "DELIVERY_SYNC_MAX_PAGES", 2)
        pages = [
            make_page([make_record("TESTDS1")], page_count=100),
            make_page([make_record("TESTDS2")], page_count=100),
        ]
        with patch_delivery_list(pages) as mock_list:
            result = await dss.sync_delivery_snapshot()

        assert result["success"] is True
        assert mock_list.call_count == 2

    @pytest.mark.asyncio
    async def test_cross_page_dedup(self, preserve_tables):
        """跨页重复的delivery_id去重(翻页期间新单插入导致)"""
        pages = [
            make_page([make_record("TESTDS1"), make_record("TESTDS2")], page_count=2),
            make_page([make_record("TESTDS2"), make_record("TESTDS3")], page_count=2),
        ]
        with patch_delivery_list(pages):
            result = await dss.sync_delivery_snapshot()

        assert result["kept_count"] == 3
        assert query_snapshot_ids() == ["TESTDS1", "TESTDS2", "TESTDS3"]

    @pytest.mark.asyncio
    async def test_page_failure_keeps_old_snapshot(self, preserve_tables):
        """某页重试耗尽 -> 整轮放弃, 旧快照保留, 状态记failed"""
        # 先成功同步一轮, 形成"旧快照"
        with patch_delivery_list([make_page([make_record("TESTDS_OLD")])]):
            assert (await dss.sync_delivery_snapshot())["success"] is True
        assert query_snapshot_ids() == ["TESTDS_OLD"]

        # 第二轮: 第1页成功, 第2页三次(1次+重试2次)全部失败
        pages = [
            make_page([make_record("TESTDS_NEW")], page_count=2),
            make_failed_page(), make_failed_page(), make_failed_page(),
        ]
        with patch_delivery_list(pages) as mock_list:
            result = await dss.sync_delivery_snapshot()

        assert result["success"] is False
        assert mock_list.call_count == 4
        # 旧快照未被破坏
        assert query_snapshot_ids() == ["TESTDS_OLD"]
        state = dss.get_sync_state()
        assert state["last_status"] == "failed"
        assert "第2页" in state["last_error"]

    @pytest.mark.asyncio
    async def test_token_insert_or_ignore(self, preserve_tables):
        """已有物流token在再次同步时保持不变"""
        with patch_delivery_list([make_page([make_record("TESTDS1")])]):
            await dss.sync_delivery_snapshot()

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT token FROM logistics_tokens WHERE logistics_name = '测试物流公司A'"
            )
            token_before = cursor.fetchone()["token"]

        with patch_delivery_list([make_page([make_record("TESTDS2")])]):
            await dss.sync_delivery_snapshot()

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT token FROM logistics_tokens WHERE logistics_name = '测试物流公司A'"
            )
            token_after = cursor.fetchone()["token"]

        assert token_before == token_after

    @pytest.mark.asyncio
    async def test_single_flight(self, preserve_tables):
        """同步进行中时再次触发直接跳过"""
        async with dss._sync_lock:
            result = await dss.sync_delivery_snapshot()
        assert result["success"] is False
        assert result["skipped"] == "running"

    @pytest.mark.asyncio
    async def test_manual_cooldown(self, preserve_tables, monkeypatch):
        """手动触发受冷却限制, 定时触发不受限"""
        monkeypatch.setattr(dss, "_last_manual_sync_ts", time.time())

        result = await dss.sync_delivery_snapshot(trigger="manual")
        assert result["skipped"] == "cooldown"

        # 定时触发不受冷却影响
        with patch_delivery_list([make_page([make_record("TESTDS1")])]):
            result = await dss.sync_delivery_snapshot(trigger="scheduled")
        assert result["success"] is True
