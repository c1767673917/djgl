"""用友云上传失败自动重试服务测试"""
import os
import sqlite3
from contextlib import contextmanager
from datetime import timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.core import yonyou_retry_service
from app.core.yonyou_retry_service import retry_failed_yonyou_uploads
from app.core.timezone import get_beijing_now_naive


@contextmanager
def db_context(db_path):
    conn = sqlite3.connect(db_path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def patch_db(db_path):
    return patch.object(
        yonyou_retry_service,
        "get_db_connection",
        side_effect=lambda: db_context(db_path),
    )


def seed_record(
    db_path,
    *,
    business_id="123456",
    doc_number="RXXOUT202606-0767",
    doc_type="销售",
    upload_type="物流",
    status="failed",
    error_code="NETWORK_ERROR",
    error_message="All connection attempts failed",
    yonyou_file_id=None,
    local_file_path=None,
    webdav_path="files/2026/06/17/x.jpg",
    retry_count=3,
    age_hours=0,
    update_age_hours=None,
    file_name="x.jpg",
):
    """插入一条记录。

    age_hours        控制 upload_time(及 created_at)距今的小时数(lookback 窗口依据)。
    update_age_hours 单独控制 updated_at; 缺省时与 upload_time 相同。
    """
    now = get_beijing_now_naive()
    upload_at = (now - timedelta(hours=age_hours)).isoformat()
    update_at = (
        now - timedelta(hours=update_age_hours if update_age_hours is not None else age_hours)
    ).isoformat()
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO upload_history
            (business_id, doc_number, doc_type, upload_type, file_name, file_size,
             file_extension, upload_time, status, error_code, error_message,
             yonyou_file_id, retry_count, local_file_path, webdav_path,
             created_at, updated_at, deleted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                business_id, doc_number, doc_type, upload_type, file_name, 1024,
                ".jpg", upload_at, status, error_code, error_message,
                yonyou_file_id, retry_count, local_file_path, webdav_path,
                upload_at, update_at, None,
            ),
        )
        conn.commit()
        return cursor.lastrowid


def get_record(db_path, record_id):
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM upload_history WHERE id = ?", (record_id,))
        return cursor.fetchone()


def make_local_file(tmp_path, content=b"img-bytes"):
    p = tmp_path / "x.jpg"
    p.write_bytes(content)
    return str(p)


@pytest.mark.asyncio
async def test_recent_network_failure_retried_to_success(test_db_path, tmp_path):
    """近期网络失败 -> 重试成功, 状态置 success 并补全 yonyou_file_id/物流。"""
    local = make_local_file(tmp_path)
    rid = seed_record(test_db_path, local_file_path=local, age_hours=1)

    yc = Mock()
    yc.upload_file = AsyncMock(return_value={"success": True, "data": {"id": "FILE_999"}})
    yc.get_delivery_detail = AsyncMock(return_value={"success": True, "logistics": "顺丰"})
    fm = Mock()
    fm.get_file = AsyncMock()  # 本地文件存在, 不应被调用

    with patch_db(test_db_path):
        stats = await retry_failed_yonyou_uploads(file_manager=fm, yonyou_client=yc)

    assert stats == {"scanned": 1, "succeeded": 1, "failed": 0, "skipped": 0}
    row = get_record(test_db_path, rid)
    assert row["status"] == "success"
    assert row["yonyou_file_id"] == "FILE_999"
    assert row["logistics"] == "顺丰"
    assert row["error_code"] is None
    assert row["error_message"] is None
    fm.get_file.assert_not_called()
    # business_type 应按 doc_type=销售 映射
    _, kwargs = yc.upload_file.call_args
    assert kwargs["business_type"] == "yonbip-scm-scmsa"


@pytest.mark.asyncio
async def test_falls_back_to_webdav_when_no_local(test_db_path):
    """本地文件缺失时从 WebDAV 取回内容。"""
    rid = seed_record(test_db_path, local_file_path=None, age_hours=2)

    yc = Mock()
    yc.upload_file = AsyncMock(return_value={"success": True, "data": {"id": "F1"}})
    yc.get_delivery_detail = AsyncMock(return_value={"success": True, "logistics": None})
    fm = Mock()
    fm.get_file = AsyncMock(return_value=b"from-webdav")

    with patch_db(test_db_path):
        stats = await retry_failed_yonyou_uploads(file_manager=fm, yonyou_client=yc)

    assert stats["succeeded"] == 1
    fm.get_file.assert_awaited_once_with("files/2026/06/17/x.jpg")
    assert get_record(test_db_path, rid)["status"] == "success"


@pytest.mark.asyncio
async def test_old_failure_excluded_by_lookback(test_db_path, tmp_path):
    """超出 lookback 窗口的历史失败不被重试(不补传旧单据)。"""
    local = make_local_file(tmp_path)
    rid = seed_record(test_db_path, local_file_path=local, age_hours=48)  # 默认窗口24h

    yc = Mock()
    yc.upload_file = AsyncMock(return_value={"success": True, "data": {"id": "F1"}})
    fm = Mock()

    with patch_db(test_db_path):
        stats = await retry_failed_yonyou_uploads(
            file_manager=fm, yonyou_client=yc, lookback_hours=24
        )

    assert stats["scanned"] == 0
    yc.upload_file.assert_not_called()
    assert get_record(test_db_path, rid)["status"] == "failed"


@pytest.mark.asyncio
async def test_non_network_error_excluded(test_db_path, tmp_path):
    """非网络类失败(业务错误)不被重试。"""
    local = make_local_file(tmp_path)
    seed_record(test_db_path, local_file_path=local, age_hours=1, error_code="310036")

    yc = Mock()
    yc.upload_file = AsyncMock()
    fm = Mock()

    with patch_db(test_db_path):
        stats = await retry_failed_yonyou_uploads(file_manager=fm, yonyou_client=yc)

    assert stats["scanned"] == 0
    yc.upload_file.assert_not_called()


@pytest.mark.asyncio
async def test_warehouse_upload_excluded(test_db_path, tmp_path):
    """仓库类上传不走用友云, 不应被重试。"""
    local = make_local_file(tmp_path)
    seed_record(test_db_path, local_file_path=local, age_hours=1, upload_type="仓库")

    yc = Mock()
    yc.upload_file = AsyncMock()
    fm = Mock()

    with patch_db(test_db_path):
        stats = await retry_failed_yonyou_uploads(file_manager=fm, yonyou_client=yc)

    assert stats["scanned"] == 0
    yc.upload_file.assert_not_called()


@pytest.mark.asyncio
async def test_still_failing_keeps_failed_and_updates_error(test_db_path, tmp_path):
    """重试仍失败 -> 保留 failed, 更新最新错误并累加 retry_count。"""
    local = make_local_file(tmp_path)
    rid = seed_record(test_db_path, local_file_path=local, age_hours=1, retry_count=3)

    yc = Mock()
    yc.upload_file = AsyncMock(
        return_value={
            "success": False,
            "error_code": "NETWORK_ERROR",
            "error_message": "Temporary failure in name resolution",
        }
    )
    fm = Mock()

    with patch_db(test_db_path):
        stats = await retry_failed_yonyou_uploads(file_manager=fm, yonyou_client=yc)

    assert stats == {"scanned": 1, "succeeded": 0, "failed": 1, "skipped": 0}
    row = get_record(test_db_path, rid)
    assert row["status"] == "failed"
    assert row["error_code"] == "NETWORK_ERROR"
    assert row["error_message"] == "Temporary failure in name resolution"
    assert row["retry_count"] == 4  # 3 -> +1
    assert row["yonyou_file_id"] is None


@pytest.mark.asyncio
async def test_business_error_on_retry_drops_out_of_pool(test_db_path, tmp_path):
    """重试时返回非网络业务错误 -> 写回新 error_code, 后续不再被选中重试。"""
    local = make_local_file(tmp_path)
    rid = seed_record(test_db_path, local_file_path=local, age_hours=1)

    yc = Mock()
    yc.upload_file = AsyncMock(
        return_value={"success": False, "error_code": "500001", "error_message": "业务校验失败"}
    )
    fm = Mock()

    with patch_db(test_db_path):
        await retry_failed_yonyou_uploads(file_manager=fm, yonyou_client=yc)
        # 第二轮: error_code 已变为业务错误, 不再被选中
        stats2 = await retry_failed_yonyou_uploads(file_manager=fm, yonyou_client=yc)

    assert stats2["scanned"] == 0
    assert get_record(test_db_path, rid)["error_code"] == "500001"


@pytest.mark.asyncio
async def test_old_upload_recent_update_excluded(test_db_path, tmp_path):
    """upload_time 很旧但 updated_at 较新(如管理员改备注/历次重试) 仍不被纳入窗口。"""
    local = make_local_file(tmp_path)
    rid = seed_record(
        test_db_path, local_file_path=local, age_hours=72, update_age_hours=1
    )

    yc = Mock()
    yc.upload_file = AsyncMock(return_value={"success": True, "data": {"id": "F1"}})
    fm = Mock()

    with patch_db(test_db_path):
        stats = await retry_failed_yonyou_uploads(
            file_manager=fm, yonyou_client=yc, lookback_hours=24
        )

    assert stats["scanned"] == 0
    yc.upload_file.assert_not_called()
    assert get_record(test_db_path, rid)["status"] == "failed"


@pytest.mark.asyncio
async def test_empty_string_yonyou_file_id_is_candidate(test_db_path, tmp_path):
    """yonyou_file_id 为空字符串(历史脏数据)也应被视为未上传成功。"""
    local = make_local_file(tmp_path)
    rid = seed_record(test_db_path, local_file_path=local, age_hours=1, yonyou_file_id="")

    yc = Mock()
    yc.upload_file = AsyncMock(return_value={"success": True, "data": {"id": "F9"}})
    yc.get_delivery_detail = AsyncMock(return_value={"success": False})
    fm = Mock()

    with patch_db(test_db_path):
        stats = await retry_failed_yonyou_uploads(file_manager=fm, yonyou_client=yc)

    assert stats["succeeded"] == 1
    assert get_record(test_db_path, rid)["yonyou_file_id"] == "F9"


@pytest.mark.asyncio
async def test_missing_file_source_marked_file_not_found(test_db_path):
    """本地与 WebDAV 均无来源 -> 标记 FILE_NOT_FOUND, 移出重试队列。"""
    rid = seed_record(test_db_path, local_file_path=None, webdav_path=None, age_hours=1)

    yc = Mock()
    yc.upload_file = AsyncMock()
    fm = Mock()
    fm.get_file = AsyncMock()

    with patch_db(test_db_path):
        stats = await retry_failed_yonyou_uploads(file_manager=fm, yonyou_client=yc)

    assert stats["skipped"] == 1
    yc.upload_file.assert_not_called()
    fm.get_file.assert_not_called()
    assert get_record(test_db_path, rid)["error_code"] == "FILE_NOT_FOUND"


@pytest.mark.asyncio
async def test_webdav_temporarily_unavailable_skips_without_changing_code(test_db_path):
    """有 webdav_path 但取文件失败(WebDAV临时不可用) -> 跳过且保留 NETWORK_ERROR 待下轮。"""
    rid = seed_record(test_db_path, local_file_path=None, age_hours=1)

    yc = Mock()
    yc.upload_file = AsyncMock()
    fm = Mock()
    fm.get_file = AsyncMock(side_effect=Exception("WebDAV 503"))

    with patch_db(test_db_path):
        stats = await retry_failed_yonyou_uploads(file_manager=fm, yonyou_client=yc)

    assert stats["skipped"] == 1
    yc.upload_file.assert_not_called()
    assert get_record(test_db_path, rid)["error_code"] == "NETWORK_ERROR"


@pytest.mark.asyncio
async def test_success_without_id_marked_invalid_response(test_db_path, tmp_path):
    """code 成功但响应缺少 id -> 标记 INVALID_RESPONSE, 不盲目重试。"""
    local = make_local_file(tmp_path)
    rid = seed_record(test_db_path, local_file_path=local, age_hours=1)

    yc = Mock()
    yc.upload_file = AsyncMock(return_value={"success": True, "data": {}})
    fm = Mock()

    with patch_db(test_db_path):
        stats = await retry_failed_yonyou_uploads(file_manager=fm, yonyou_client=yc)

    assert stats["failed"] == 1
    row = get_record(test_db_path, rid)
    assert row["status"] == "failed"
    assert row["error_code"] == "INVALID_RESPONSE"


@pytest.mark.asyncio
async def test_one_bad_record_does_not_abort_batch(test_db_path, tmp_path):
    """单条记录处理抛异常不应中断整轮, 其余记录仍被处理。"""
    local = make_local_file(tmp_path)
    bad = seed_record(test_db_path, doc_number="BAD", local_file_path=local, age_hours=2)
    good = seed_record(test_db_path, doc_number="GOOD", local_file_path=local, age_hours=1)

    # 第一条 upload_file 抛异常被捕获并写回, 但 get_delivery_detail 对第二条正常
    yc = Mock()
    yc.upload_file = AsyncMock(
        side_effect=[
            RuntimeError("boom"),
            {"success": True, "data": {"id": "OK"}},
        ]
    )
    yc.get_delivery_detail = AsyncMock(return_value={"success": True, "logistics": "中通"})
    fm = Mock()

    with patch_db(test_db_path):
        stats = await retry_failed_yonyou_uploads(file_manager=fm, yonyou_client=yc)

    # 排序 updated_at ASC: bad(更旧)先, good 后; 两条都被处理
    assert stats["scanned"] == 2
    assert stats["succeeded"] == 1
    assert get_record(test_db_path, good)["status"] == "success"
    assert get_record(test_db_path, bad)["status"] == "failed"
