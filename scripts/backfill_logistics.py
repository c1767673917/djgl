#!/usr/bin/env python3
"""
根据上传记录中的 business_id 调用用友云接口，补全 upload_history.logistics 字段。

用法：
    在项目根目录下执行：

        python scripts/backfill_logistics.py

脚本会：
    1. 读取 .env 配置（通过 app.core.config.Settings 自动完成）
    2. 找出所有 logistics 为空、business_id 有值的记录
    3. 调用 YonYouClient.get_delivery_detail(business_id)
    4. 成功时将返回的物流公司名称写入 upload_history.logistics
"""

import asyncio
import sys
from pathlib import Path
from typing import List, Tuple

# 将项目根目录加入 sys.path，方便导入 app.*
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.database import get_db_connection  # type: ignore  # noqa: E402
from app.core.yonyou_client import YonYouClient  # type: ignore  # noqa: E402
from app.core.timezone import get_beijing_now_naive  # type: ignore  # noqa: E402


# 接口限流：40 次/分钟，为安全起见，控制在略低于 40 次
RATE_LIMIT_CALLS_PER_MINUTE = 40
SAFETY_MARGIN_SECONDS = 0.1
PER_CALL_DELAY = 60.0 / RATE_LIMIT_CALLS_PER_MINUTE + SAFETY_MARGIN_SECONDS


async def fetch_pending_records() -> List[Tuple[int, str]]:
    """查询所有需要补全物流信息的记录"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, business_id
            FROM upload_history
            WHERE (logistics IS NULL OR logistics = '')
              AND business_id IS NOT NULL
              AND business_id != ''
              AND deleted_at IS NULL
            ORDER BY id ASC
            """
        )
        rows = cursor.fetchall()

    pending: List[Tuple[int, str]] = [(row[0], row[1]) for row in rows]
    return pending


async def update_single_record(
    client: YonYouClient,
    record_id: int,
    business_id: str,
) -> bool:
    """
    为单条记录查询并更新物流信息。

    返回 True 表示成功写入（包括物流为空但调用成功的情况），False 表示调用失败。
    """
    print(f"  -> 查询业务ID {business_id} 的物流信息...")
    result = await client.get_delivery_detail(business_id)

    if not result.get("success"):
        print(
            f"     ✗ 查询失败: id={record_id}, "
            f"business_id={business_id}, "
            f"error_code={result.get('error_code')}, "
            f"message={result.get('error_message')}"
        )
        return False

    logistics = result.get("logistics")

    # 写回数据库
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE upload_history
            SET logistics = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (logistics, get_beijing_now_naive().isoformat(), record_id),
        )
        conn.commit()

    print(
        f"     ✓ 更新成功: id={record_id}, business_id={business_id}, "
        f"logistics={logistics or '(空)'}"
    )
    return True


async def main() -> None:
    # 查询待处理记录
    pending_records = await fetch_pending_records()
    total = len(pending_records)

    if total == 0:
        print("当前没有需要补全物流信息的记录。")
        return

    print(f"共找到 {total} 条 logistics 为空且 business_id 有值的记录，将逐条尝试补全。")
    print("提示：接口默认限流 40 次/分钟，脚本会控制调用频率，请耐心等待执行完成。")

    client = YonYouClient()

    succeeded = 0
    failed = 0

    for idx, (record_id, business_id) in enumerate(pending_records, start=1):
        print(f"\n[{idx}/{total}] 处理记录 id={record_id}, business_id={business_id}")
        try:
            ok = await update_single_record(client, record_id, business_id)
            if ok:
                succeeded += 1
            else:
                failed += 1
        except Exception as exc:  # 兜底异常，避免单条失败中断整个脚本
            failed += 1
            print(f"     ✗ 处理异常: {exc}")

        # 严格控制调用频率，避免超过 40 次/分钟
        if idx < total:
            await asyncio.sleep(PER_CALL_DELAY)

    print("\n===== 补全完成 =====")
    print(f"总记录数: {total}")
    print(f"成功更新: {succeeded}")
    print(f"失败/未更新: {failed}")


if __name__ == "__main__":
    asyncio.run(main())
