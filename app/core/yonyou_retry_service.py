"""
用友云上传失败自动重试服务

背景:
    个别单据在上传到用友云(c4.yonyoucloud.com)时遇到瞬时 DNS/网络抖动,
    httpx 在拿到 HTTP 响应之前就抛异常, ``YonYouClient.upload_file`` 把这类异常
    统一记为 ``error_code='NETWORK_ERROR'``。``background_upload_to_yonyou`` 在
    ``MAX_RETRY_COUNT`` 次重试后仍失败便把记录置为 ``status='failed'``。
    这类失败是短时网络问题, 而文件本身已经保存在 WebDAV/本地。

策略:
    定时(默认每小时)扫描"近期"(默认 24 小时内) ``status='failed'`` 且
    ``error_code='NETWORK_ERROR'`` 的物流类记录, 从本地或 WebDAV 取回文件重新上传到
    用友云。成功则置 ``success`` 并补全 ``yonyou_file_id`` 与物流信息; 仍失败则保留
    ``failed`` 等待下一轮重试, 形成"每小时重试直到成功"的效果。

    "仅处理近期失败" => 不会回头去补传很久以前的历史失败单据(由 lookback 窗口控制)。
    若某条记录重试后返回的是非网络类业务错误, 会写回新的 error_code, 从而自动移出
    重试队列, 避免对真正的业务失败无限重试。

注意:
    项目的 ``get_db_connection`` 在整个 ``with`` 块期间持有全局数据库锁, 因此本服务
    刻意做到 **不在网络 I/O 期间持有数据库连接**: 先一次性查出候选记录并释放连接,
    再逐条上传, 每条上传完单独开连接更新, 避免阻塞其它数据库操作。
"""

import logging
import os
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import get_settings
from app.core.database import get_db_connection
from app.core.file_manager import FileManager
from app.core.timezone import get_beijing_now_naive
from app.core.upload_types import (
    DEFAULT_UPLOAD_TYPE,
    DOC_TYPE_TO_BUSINESS_TYPE,
    UPLOAD_TYPE_LOGISTICS,
)
from app.core.yonyou_client import YonYouClient

logger = logging.getLogger(__name__)
settings = get_settings()


async def _load_file_content(
    file_manager: FileManager,
    local_file_path: Optional[str],
    webdav_path: Optional[str],
) -> bytes:
    """取回待上传文件内容: 优先本地备份, 其次 WebDAV。"""
    if local_file_path and os.path.exists(local_file_path):
        with open(local_file_path, "rb") as f:
            return f.read()
    if webdav_path:
        return await file_manager.get_file(webdav_path)
    raise FileNotFoundError("本地文件与 webdav_path 均不可用")


def _fetch_candidates(lookback_hours: int, max_records: int) -> List[Tuple]:
    """查询近期因网络瞬时故障而失败、尚未上传成功的物流类记录。

    lookback 窗口用 ``upload_time`` (单据上传时间, 不随后续编辑/重试变化) 判定,
    而不是 ``updated_at``:
        - ``updated_at`` 会被管理员改备注/检查状态, 以及本服务每轮重试刷新, 用它做窗口
          会把历史失败单据反复拉回队列, 也会让持续失败的记录因每次重试刷新时间而"永不出窗"。
    排序用 ``updated_at ASC`` (最久未尝试者优先), 避免靠前的失败记录长期占用名额导致饥饿。
    """
    cutoff = (get_beijing_now_naive() - timedelta(hours=lookback_hours)).isoformat()

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, business_id, doc_number, doc_type, file_name,
                   local_file_path, webdav_path, retry_count
            FROM upload_history
            WHERE status = 'failed'
              AND error_code = 'NETWORK_ERROR'
              AND NULLIF(yonyou_file_id, '') IS NULL
              AND deleted_at IS NULL
              AND COALESCE(NULLIF(upload_type, ''), ?) = ?
              AND upload_time >= ?
            ORDER BY updated_at ASC, id ASC
            LIMIT ?
            """,
            (DEFAULT_UPLOAD_TYPE, UPLOAD_TYPE_LOGISTICS, cutoff, max_records),
        )
        # 立即取出并转为普通元组, 释放连接(及全局数据库锁)后再做网络上传
        return [tuple(row) for row in cursor.fetchall()]


def _mark_success(
    record_id: int,
    yonyou_file_id: str,
    logistics: Optional[str],
    customer_name: Optional[str],
    retry_count: int,
) -> int:
    """置为成功; 返回受影响行数。

    WHERE 条件与候选筛选保持一致(仍为待重试的网络失败、未删除、尚无 file id),
    避免候选查询后记录被软删除或被其它流程改写时仍被误更新。
    """
    now_iso = get_beijing_now_naive().isoformat()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        # webdav_path / is_cached 等字段沿用原始上传的结果, 这里只更新用友相关字段
        cursor.execute(
            """
            UPDATE upload_history
            SET status = 'success',
                yonyou_file_id = ?,
                logistics = ?,
                customer_name = ?,
                error_code = NULL,
                error_message = NULL,
                retry_count = ?,
                updated_at = ?
            WHERE id = ?
              AND status = 'failed'
              AND error_code = 'NETWORK_ERROR'
              AND NULLIF(yonyou_file_id, '') IS NULL
              AND deleted_at IS NULL
            """,
            (yonyou_file_id, logistics, customer_name, retry_count, now_iso, record_id),
        )
        conn.commit()
        return cursor.rowcount


def _mark_still_failed(
    record_id: int,
    error_code: Optional[str],
    error_message: Optional[str],
    retry_count: int,
) -> int:
    """记录最新失败信息(状态仍为 failed); 返回受影响行数。"""
    now_iso = get_beijing_now_naive().isoformat()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE upload_history
            SET error_code = ?,
                error_message = ?,
                retry_count = ?,
                updated_at = ?
            WHERE id = ? AND status = 'failed' AND deleted_at IS NULL
            """,
            (error_code, error_message, retry_count, now_iso, record_id),
        )
        conn.commit()
        return cursor.rowcount


async def retry_failed_yonyou_uploads(
    *,
    file_manager: Optional[FileManager] = None,
    yonyou_client: Optional[YonYouClient] = None,
    lookback_hours: Optional[int] = None,
    max_records: Optional[int] = None,
) -> Dict[str, Any]:
    """扫描并重试近期因网络瞬时故障失败的用友云上传。

    Returns:
        统计字典: {scanned, succeeded, failed, skipped}
    """
    lookback_hours = lookback_hours if lookback_hours is not None else settings.YONYOU_RETRY_LOOKBACK_HOURS
    max_records = max_records if max_records is not None else settings.YONYOU_RETRY_MAX_RECORDS

    fm = file_manager or FileManager()
    yc = yonyou_client or YonYouClient()

    candidates = _fetch_candidates(lookback_hours, max_records)
    stats = {"scanned": len(candidates), "succeeded": 0, "failed": 0, "skipped": 0}

    if not candidates:
        return stats

    logger.info(f"[用友重试] 发现 {len(candidates)} 条近期网络失败记录, 开始重试")

    for (
        record_id,
        business_id,
        doc_number,
        doc_type,
        file_name,
        local_file_path,
        webdav_path,
        retry_count,
    ) in candidates:
        # 单条记录的任何异常都不应中断整轮任务
        try:
            new_retry_count = (retry_count or 0) + 1

            # 1. 取回文件内容(本地优先, 其次 WebDAV)
            has_local = bool(local_file_path and os.path.exists(local_file_path))
            if not has_local and not webdav_path:
                # 本地与 WebDAV 均无可取来源 => 不可恢复, 写回 FILE_NOT_FOUND 移出重试队列
                _mark_still_failed(
                    record_id, "FILE_NOT_FOUND", "本地文件与 webdav_path 均不可用", new_retry_count
                )
                stats["skipped"] += 1
                logger.warning(
                    f"[用友重试] 文件来源缺失, 标记 FILE_NOT_FOUND id={record_id} doc={doc_number}"
                )
                continue

            try:
                file_content = await _load_file_content(fm, local_file_path, webdav_path)
            except Exception as e:  # noqa: BLE001
                # 取文件失败可能是 WebDAV 临时不可用, 保留原错误码, 跳过本轮下次再试
                stats["skipped"] += 1
                logger.warning(
                    f"[用友重试] 取文件失败, 跳过本轮 id={record_id} doc={doc_number}: {e}"
                )
                continue

            # 2. 重新上传到用友云
            business_type = DOC_TYPE_TO_BUSINESS_TYPE.get(
                doc_type, settings.YONYOU_BUSINESS_TYPE
            )
            try:
                result = await yc.upload_file(
                    file_content,
                    file_name,
                    business_id,
                    business_type=business_type,
                )
            except Exception as e:  # noqa: BLE001
                stats["failed"] += 1
                _mark_still_failed(record_id, "NETWORK_ERROR", str(e), new_retry_count)
                logger.warning(f"[用友重试] 上传异常 id={record_id} doc={doc_number}: {e}")
                continue

            if not result.get("success"):
                error_code = result.get("error_code")
                error_message = result.get("error_message")
                stats["failed"] += 1
                _mark_still_failed(record_id, error_code, error_message, new_retry_count)
                logger.warning(
                    f"[用友重试] 仍失败 id={record_id} doc={doc_number} "
                    f"code={error_code} msg={error_message}"
                )
                continue

            # 3. 上传成功, 校验响应中的 file id
            data = result.get("data") or {}
            yonyou_file_id = data.get("id") if isinstance(data, dict) else None
            if not yonyou_file_id:
                # code 成功但响应缺少 id: 附件可能已创建, 不可盲目重试, 移出队列待人工核查
                stats["failed"] += 1
                _mark_still_failed(
                    record_id, "INVALID_RESPONSE", f"上传成功但响应缺少 id: {result}", new_retry_count
                )
                logger.warning(f"[用友重试] 响应缺少 file id id={record_id} doc={doc_number}")
                continue

            # 4. 补全物流信息和客户名称(失败不影响主流程)
            logistics = None
            customer_name = None
            if business_id:
                try:
                    detail = await yc.get_delivery_detail(business_id)
                    if detail.get("success"):
                        logistics = detail.get("logistics")
                        customer_name = detail.get("customer_name")
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"[用友重试] 发货单详情查询异常 id={record_id}: {e}")

            updated = _mark_success(record_id, yonyou_file_id, logistics, customer_name, new_retry_count)
            if updated:
                stats["succeeded"] += 1
                logger.info(
                    f"[用友重试] 成功 id={record_id} doc={doc_number} file_id={yonyou_file_id}"
                )
            else:
                # 候选查询后记录已被其它流程改写(软删除/已成功等), 跳过
                stats["skipped"] += 1
                logger.info(f"[用友重试] 记录已变更, 跳过更新 id={record_id} doc={doc_number}")

        except Exception as e:  # noqa: BLE001
            stats["failed"] += 1
            logger.error(f"[用友重试] 处理记录异常 id={record_id} doc={doc_number}: {e}")

    logger.info(
        f"[用友重试] 完成: 扫描{stats['scanned']} 成功{stats['succeeded']} "
        f"仍失败{stats['failed']} 跳过{stats['skipped']}"
    )
    return stats
