from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
from app.core.database import get_db_connection

router = APIRouter()


@router.get("/history/{business_id}")
async def get_upload_history(business_id: str) -> Dict[str, Any]:
    """
    查询指定业务单据的上传历史

    响应格式:
    {
        "business_id": "000000",
        "total_count": 15,
        "success_count": 14,
        "failed_count": 1,
        "records": [...]
    }
    """
    # 使用上下文管理器确保连接正确关闭
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # 查询记录
        cursor.execute("""
            SELECT id, file_name, file_size, file_extension, upload_time,
                   status, error_code, error_message, yonyou_file_id, retry_count
            FROM upload_history
            WHERE business_id = ?
            ORDER BY upload_time DESC
        """, (business_id,))

        rows = cursor.fetchall()

    if not rows:
        return {
            "business_id": business_id,
            "total_count": 0,
            "success_count": 0,
            "failed_count": 0,
            "records": []
        }

    # 转换为字典列表
    records = []
    success_count = 0
    failed_count = 0

    for row in rows:
        record = {
            "id": row[0],
            "file_name": row[1],
            "file_size": row[2],
            "file_extension": row[3],
            "upload_time": row[4],
            "status": row[5],
            "error_code": row[6],
            "error_message": row[7],
            "yonyou_file_id": row[8],
            "retry_count": row[9]
        }
        records.append(record)

        if row[5] == "success":
            success_count += 1
        else:
            failed_count += 1

    return {
        "business_id": business_id,
        "total_count": len(records),
        "success_count": success_count,
        "failed_count": failed_count,
        "records": records
    }
