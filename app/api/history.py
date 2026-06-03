from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any, Optional
from app.core.database import get_db_connection
from app.core.upload_types import (
    DEFAULT_UPLOAD_TYPE,
    UPLOAD_TYPE_LOGISTICS,
    UPLOAD_TYPE_WAREHOUSE,
    VALID_UPLOAD_TYPES,
)

router = APIRouter()


@router.get("/history/{business_id}")
async def get_upload_history(
    business_id: str,
    upload_type: Optional[str] = Query(None, description="上传业务类型筛选")
) -> Dict[str, Any]:
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
    upload_type_value = (upload_type or "").strip()
    if upload_type_value and upload_type_value not in VALID_UPLOAD_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"upload_type必须为以下值之一: {', '.join(sorted(VALID_UPLOAD_TYPES))}"
        )

    # 使用上下文管理器确保连接正确关闭
    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("PRAGMA table_info(upload_history)")
        columns = {col[1] for col in cursor.fetchall()}
        has_upload_type = "upload_type" in columns
        upload_type_select = (
            "COALESCE(NULLIF(upload_type, ''), ?) AS upload_type"
            if has_upload_type
            else "? AS upload_type"
        )

        where_clauses = ["business_id = ?", "deleted_at IS NULL"]
        params = [business_id]
        if upload_type_value == UPLOAD_TYPE_LOGISTICS and has_upload_type:
            where_clauses.append("COALESCE(NULLIF(upload_type, ''), ?) = ?")
            params.extend([DEFAULT_UPLOAD_TYPE, UPLOAD_TYPE_LOGISTICS])
        elif upload_type_value == UPLOAD_TYPE_WAREHOUSE and has_upload_type:
            where_clauses.append("upload_type = ?")
            params.append(UPLOAD_TYPE_WAREHOUSE)
        elif upload_type_value == UPLOAD_TYPE_WAREHOUSE:
            where_clauses.append("1 = 0")

        where_sql = " AND ".join(where_clauses)

        # 查询记录
        cursor.execute(f"""
            SELECT id, file_name, file_size, file_extension, upload_time,
                   status, error_code, error_message, yonyou_file_id, retry_count,
                   {upload_type_select}
            FROM upload_history
            WHERE {where_sql}
            ORDER BY upload_time DESC
        """, [DEFAULT_UPLOAD_TYPE] + params)

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
            "retry_count": row[9],
            "upload_type": row[10]
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
