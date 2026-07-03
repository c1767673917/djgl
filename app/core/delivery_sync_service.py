"""
发货单快照同步服务 (物流待上传门户数据源)

背景:
    物流公司经常漏传回单, 管理员需要给每家物流公司一个专属链接, 让对方自查
    "过去两个月内还没上传回单的发货单"。数据源是用友"销售发货列表"接口。

策略:
    定时(默认30分钟)从用友拉取过去 N 天的发货单表头(isSum=true, 每单一行),
    本地过滤"供应商非自提 且 运费大于阈值"后, 单事务全量替换 delivery_snapshot 表,
    并为新出现的物流公司自动生成专属 token (INSERT OR IGNORE)。

    - 服务端 simpleVOs 对自定义字段(deliveryVoucherDefineCharacter)过滤不生效(实测),
      供应商(RX003_name)与运费(RX004)只能拉全量后本地过滤。
    - "已上传排除"不烘焙进快照, 由门户查询时对 upload_history 做 NOT EXISTS 实时计算,
      物流传完回单立刻从列表消失。
    - 任一页最终失败则整轮放弃, 保留旧快照(陈旧但完整), 同步状态写入 app_meta。

注意:
    项目的 ``get_db_connection`` 在整个 with 块期间持有全局数据库锁, 因此本服务
    先把所有页拉到内存, 全部成功后才开数据库连接落库, 持锁期间不做任何网络 I/O。
"""

import asyncio
import logging
import secrets
import time
import urllib.parse
from datetime import timedelta
from typing import Any, Dict, List, Optional

from app.core.config import get_settings
from app.core.database import get_db_connection
from app.core.timezone import get_beijing_now_naive
from app.core.upload_types import DEFAULT_UPLOAD_TYPE, UPLOAD_TYPE_LOGISTICS
from app.core.yonyou_client import YonYouClient

logger = logging.getLogger(__name__)
settings = get_settings()

# 单飞互斥: 同一时刻只允许一轮同步(定时与手动共用)
_sync_lock = asyncio.Lock()
# 手动同步冷却(进程内即可, 冷却只是防管理员连点)
_last_manual_sync_ts: float = 0.0

# 每页失败重试的等待秒数(重试2次)
_PAGE_RETRY_DELAYS = [2, 5]

META_LAST_AT = "delivery_sync_last_at"
META_STATUS = "delivery_sync_status"
META_ERROR = "delivery_sync_error"
META_RECORD_COUNT = "delivery_sync_record_count"


class SyncFetchError(Exception):
    """拉取用友发货列表最终失败(重试耗尽)"""


def is_sync_running() -> bool:
    return _sync_lock.locked()


def get_manual_cooldown_remaining() -> int:
    """手动同步冷却剩余秒数, 0表示可触发"""
    elapsed = time.time() - _last_manual_sync_ts
    remaining = settings.DELIVERY_SYNC_MANUAL_COOLDOWN_SECONDS - elapsed
    return max(0, int(remaining))


async def sync_delivery_snapshot(trigger: str = "scheduled") -> Dict[str, Any]:
    """执行一轮快照同步

    Args:
        trigger: "scheduled" 定时触发 / "manual" 管理页手动触发

    Returns:
        {"success", "skipped", "pages", "raw_count", "kept_count", "duration_ms", "error"}
    """
    global _last_manual_sync_ts

    if _sync_lock.locked():
        return {"success": False, "skipped": "running", "error": "同步正在进行中"}

    if trigger == "manual":
        remaining = get_manual_cooldown_remaining()
        if remaining > 0:
            return {
                "success": False,
                "skipped": "cooldown",
                "error": f"请{remaining}秒后再试",
            }
        _last_manual_sync_ts = time.time()

    async with _sync_lock:
        started = time.monotonic()
        now = get_beijing_now_naive()
        begin = (now - timedelta(days=settings.DELIVERY_SYNC_LOOKBACK_DAYS)).strftime(
            "%Y-%m-%d 00:00:00"
        )
        end = now.strftime("%Y-%m-%d 23:59:59")

        try:
            client = YonYouClient()
            raw_records, pages = await _fetch_all_pages(client, begin, end)
            kept = _extract_and_filter(raw_records)
            _replace_snapshot_and_tokens(kept)

            duration_ms = int((time.monotonic() - started) * 1000)
            logger.info(
                f"发货单快照同步完成({trigger}): 窗口{begin}~{end}, "
                f"{pages}页/{len(raw_records)}行原始, 过滤后保留{len(kept)}张, 耗时{duration_ms}ms"
            )
            return {
                "success": True,
                "skipped": None,
                "pages": pages,
                "raw_count": len(raw_records),
                "kept_count": len(kept),
                "duration_ms": duration_ms,
                "error": None,
            }
        except Exception as exc:
            duration_ms = int((time.monotonic() - started) * 1000)
            logger.error(f"发货单快照同步失败({trigger}): {exc}, 保留旧快照")
            _set_sync_meta("failed", str(exc))
            return {
                "success": False,
                "skipped": None,
                "duration_ms": duration_ms,
                "error": str(exc),
            }


async def _fetch_all_pages(
    client: YonYouClient, begin: str, end: str
) -> tuple:
    """逐页拉取全部表头行, 返回 (records, pages_fetched)。任一页最终失败抛 SyncFetchError。"""
    all_records: List[dict] = []
    page_size = settings.DELIVERY_SYNC_PAGE_SIZE
    max_pages = settings.DELIVERY_SYNC_MAX_PAGES

    first = await _fetch_page_with_retry(client, 1, page_size, begin, end)
    all_records.extend(first["records"])
    page_count = min(first["page_count"] or 0, max_pages)
    if first["page_count"] and first["page_count"] > max_pages:
        logger.warning(
            f"发货列表页数{first['page_count']}超过上限{max_pages}, 仅拉取前{max_pages}页"
        )

    pages_fetched = 1
    for page_index in range(2, page_count + 1):
        await asyncio.sleep(settings.DELIVERY_SYNC_PAGE_INTERVAL_SECONDS)
        page = await _fetch_page_with_retry(client, page_index, page_size, begin, end)
        pages_fetched += 1
        if not page["records"]:
            # pageCount 可能因同步期间数据变动而漂移, 空页视为拉完
            break
        all_records.extend(page["records"])

    return all_records, pages_fetched


async def _fetch_page_with_retry(
    client: YonYouClient, page_index: int, page_size: int, begin: str, end: str
) -> Dict[str, Any]:
    last_error = None
    for attempt in range(len(_PAGE_RETRY_DELAYS) + 1):
        result = await client.get_delivery_list(page_index, page_size, begin, end)
        if result["success"]:
            return result
        last_error = f"{result['error_code']}: {result['error_message']}"
        if attempt < len(_PAGE_RETRY_DELAYS):
            logger.warning(
                f"发货列表第{page_index}页拉取失败({last_error}), "
                f"{_PAGE_RETRY_DELAYS[attempt]}秒后重试"
            )
            await asyncio.sleep(_PAGE_RETRY_DELAYS[attempt])
    raise SyncFetchError(f"第{page_index}页拉取失败: {last_error}")


def _parse_freight(value: Any) -> float:
    try:
        return float(str(value).replace(",", "").strip())
    except (ValueError, TypeError):
        return 0.0


def _extract_and_filter(raw_records: List[dict]) -> List[Dict[str, Any]]:
    """本地过滤 + 字段提取 + 按 delivery_id 去重

    保留条件: 供应商(RX003_name)非空且不含"自提", 且运费(RX004) > 阈值。
    """
    kept: Dict[str, Dict[str, Any]] = {}
    for rec in raw_records:
        define_character = rec.get("deliveryVoucherDefineCharacter") or {}
        logistics = str(define_character.get("RX003_name") or "").strip()
        if not logistics or "自提" in logistics:
            continue

        freight = _parse_freight(define_character.get("RX004"))
        if freight <= settings.DELIVERY_SYNC_MIN_FREIGHT:
            continue

        delivery_id = rec.get("id")
        if delivery_id is None:
            continue
        # 用友id为19位长整型, 全链路按字符串处理防精度丢失
        delivery_id = str(delivery_id)

        vouchdate = str(rec.get("vouchdate") or "")[:10]

        kept[delivery_id] = {
            "delivery_id": delivery_id,
            "delivery_code": rec.get("code"),
            "customer_name": rec.get("agentId_name"),
            "vouchdate": vouchdate,
            "logistics_name": logistics,
            "freight": freight,
        }
    return list(kept.values())


def _replace_snapshot_and_tokens(rows: List[Dict[str, Any]]) -> None:
    """单事务全量替换快照, 并为新物流名生成token, 更新同步状态元数据"""
    now_iso = get_beijing_now_naive().isoformat()
    logistics_names = sorted({row["logistics_name"] for row in rows})

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM delivery_snapshot")
        cursor.executemany(
            """
            INSERT INTO delivery_snapshot
                (delivery_id, delivery_code, customer_name, vouchdate,
                 logistics_name, freight, synced_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row["delivery_id"],
                    row["delivery_code"],
                    row["customer_name"],
                    row["vouchdate"],
                    row["logistics_name"],
                    row["freight"],
                    now_iso,
                )
                for row in rows
            ],
        )

        for name in logistics_names:
            cursor.execute(
                """
                INSERT OR IGNORE INTO logistics_tokens
                    (logistics_name, token, enabled, created_at, updated_at)
                VALUES (?, ?, 1, ?, ?)
                """,
                (name, secrets.token_urlsafe(16), now_iso, now_iso),
            )

        _write_meta(cursor, META_LAST_AT, now_iso)
        _write_meta(cursor, META_STATUS, "success")
        _write_meta(cursor, META_ERROR, "")
        _write_meta(cursor, META_RECORD_COUNT, str(len(rows)))
        conn.commit()


def _set_sync_meta(status: str, error: str) -> None:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        _write_meta(cursor, META_STATUS, status)
        _write_meta(cursor, META_ERROR, error)
        conn.commit()


def _write_meta(cursor, key: str, value: str) -> None:
    cursor.execute(
        "INSERT INTO app_meta (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def get_sync_state() -> Dict[str, Any]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT key, value FROM app_meta WHERE key IN (?, ?, ?, ?)",
            (META_LAST_AT, META_STATUS, META_ERROR, META_RECORD_COUNT),
        )
        meta = {row["key"]: row["value"] for row in cursor.fetchall()}

    record_count = meta.get(META_RECORD_COUNT)
    return {
        "running": is_sync_running(),
        "last_sync_at": meta.get(META_LAST_AT),
        "last_status": meta.get(META_STATUS),
        "last_error": meta.get(META_ERROR) or None,
        "record_count": int(record_count) if record_count else 0,
    }


# 门户查询里"已上传排除"的统一条件:
# upload_history 存在任意未删除的**物流类**记录(不限status, 失败推送有每小时自动重试兜底)即算已上传。
# 仓库上传(upload_type='仓库')是另一业务, 同号不代表物流回单已传, 不参与排除;
# 历史记录 upload_type 为 NULL/空串时按默认"物流"对待(与 admin/history/retry 各处口径一致)。
_NOT_UPLOADED_CONDITION = f"""
    NOT EXISTS (
        SELECT 1 FROM upload_history u
        WHERE u.deleted_at IS NULL
          AND COALESCE(NULLIF(u.upload_type, ''), '{DEFAULT_UPLOAD_TYPE}') = '{UPLOAD_TYPE_LOGISTICS}'
          AND (u.business_id = s.delivery_id OR u.doc_number = s.delivery_code)
    )
"""


def list_links_with_pending() -> List[Dict[str, Any]]:
    """管理侧: 全部物流链接及各自待上传单据数"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT t.id, t.logistics_name, t.token, t.enabled,
                   t.created_at, t.last_access_at,
                   (SELECT COUNT(*) FROM delivery_snapshot s
                    WHERE s.logistics_name = t.logistics_name
                      AND {_NOT_UPLOADED_CONDITION}) AS pending_count
            FROM logistics_tokens t
            ORDER BY pending_count DESC, t.logistics_name ASC
            """
        )
        return [
            {
                "id": row["id"],
                "logistics_name": row["logistics_name"],
                "token": row["token"],
                "enabled": bool(row["enabled"]),
                "created_at": row["created_at"],
                "last_access_at": row["last_access_at"],
                "pending_count": row["pending_count"],
                "link_path": f"/l/{row['token']}",
            }
            for row in cursor.fetchall()
        ]


def regenerate_token(link_id: int) -> Optional[str]:
    """重置指定物流的token, 旧链接立即失效。返回新token, 不存在返回None"""
    new_token = secrets.token_urlsafe(16)
    now_iso = get_beijing_now_naive().isoformat()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE logistics_tokens SET token = ?, updated_at = ? WHERE id = ?",
            (new_token, now_iso, link_id),
        )
        if cursor.rowcount == 0:
            return None
        conn.commit()
    return new_token


def get_token_row(token: str) -> Optional[Dict[str, Any]]:
    """按token查有效(enabled)的物流链接记录"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, logistics_name FROM logistics_tokens "
            "WHERE token = ? AND enabled = 1",
            (token,),
        )
        row = cursor.fetchone()
        return {"id": row["id"], "logistics_name": row["logistics_name"]} if row else None


def get_portal_data(token: str) -> Optional[Dict[str, Any]]:
    """物流侧: 该物流公司的待上传单据清单。token无效/禁用返回None"""
    token_row = get_token_row(token)
    if not token_row:
        return None

    now_iso = get_beijing_now_naive().isoformat()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE logistics_tokens SET last_access_at = ? WHERE id = ?",
            (now_iso, token_row["id"]),
        )
        cursor.execute(
            f"""
            SELECT s.delivery_id, s.delivery_code, s.customer_name,
                   s.vouchdate
            FROM delivery_snapshot s
            WHERE s.logistics_name = ?
              AND {_NOT_UPLOADED_CONDITION}
            ORDER BY s.vouchdate ASC, s.delivery_code ASC
            """,
            (token_row["logistics_name"],),
        )
        deliveries = [
            {
                "delivery_id": row["delivery_id"],
                "delivery_code": row["delivery_code"],
                "customer_name": row["customer_name"],
                "vouchdate": row["vouchdate"],
                "upload_url": "/?" + urllib.parse.urlencode(
                    {
                        "business_id": row["delivery_id"],
                        "doc_number": row["delivery_code"] or "",
                        "doc_type": "销售",
                    }
                ),
            }
            for row in cursor.fetchall()
        ]
        conn.commit()

    state = get_sync_state()
    return {
        "logistics_name": token_row["logistics_name"],
        "last_sync_at": state["last_sync_at"],
        "total": len(deliveries),
        "deliveries": deliveries,
    }
