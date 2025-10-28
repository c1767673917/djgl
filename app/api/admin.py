from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from typing import List, Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel
import csv
import io
import os
import zipfile
import tempfile
from pathlib import Path
from openpyxl import Workbook
from app.core.database import get_db_connection
from app.core.config import get_settings
from app.core.timezone import get_beijing_now_naive

settings = get_settings()
router = APIRouter()


@router.get("/records")
async def get_admin_records(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页记录数"),
    search: Optional[str] = Query(None, description="搜索关键词（单据编号/类型）"),
    doc_type: Optional[str] = Query(None, description="单据类型筛选"),
    product_type: Optional[str] = Query(None, description="产品类型筛选(如:油脂/快消)"),
    status: Optional[str] = Query(None, description="状态筛选（pending/uploading/success/failed）"),
    start_date: Optional[str] = Query(None, description="开始日期（YYYY-MM-DD）"),
    end_date: Optional[str] = Query(None, description="结束日期（YYYY-MM-DD）")
) -> Dict[str, Any]:
    """
    获取上传记录列表（管理页面）

    查询参数:
    - page: 页码（从1开始）
    - page_size: 每页记录数（默认20，最大100）
    - search: 搜索关键词（模糊匹配单据编号或文件名）
    - doc_type: 单据类型筛选（销售/转库/其他）
    - product_type: 产品类型筛选（油脂/快消）
    - status: 状态筛选（pending/uploading/success/failed）
    - start_date: 开始日期（格式：YYYY-MM-DD）
    - end_date: 结束日期（格式：YYYY-MM-DD）

    响应格式:
    {
        "total": 150,
        "page": 1,
        "page_size": 20,
        "total_pages": 8,
        "records": [...]
    }
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # 构建WHERE条件（移除硬编码的status过滤，支持动态筛选）
        where_clauses = ["deleted_at IS NULL"]
        params = []

        if search:
            where_clauses.append("(doc_number LIKE ? OR file_name LIKE ?)")
            search_pattern = f"%{search}%"
            params.extend([search_pattern, search_pattern])

        if doc_type:
            where_clauses.append("doc_type = ?")
            params.append(doc_type)

        if product_type:
            where_clauses.append("product_type = ?")
            params.append(product_type)

        if status:
            where_clauses.append("status = ?")
            params.append(status)

        if start_date:
            where_clauses.append("DATE(upload_time) >= ?")
            params.append(start_date)

        if end_date:
            where_clauses.append("DATE(upload_time) <= ?")
            params.append(end_date)

        where_sql = " AND ".join(where_clauses)

        # 查询总记录数
        cursor.execute(f"SELECT COUNT(*) FROM upload_history WHERE {where_sql}", params)
        total = cursor.fetchone()[0]

        # 计算分页
        total_pages = (total + page_size - 1) // page_size
        offset = (page - 1) * page_size

        # 查询分页数据（包含status、error_code、checked和notes字段）
        cursor.execute(f"""
            SELECT id, business_id, doc_number, doc_type, product_type, file_name, file_size,
                   upload_time, status, error_code, error_message, checked, notes
            FROM upload_history
            WHERE {where_sql}
            ORDER BY upload_time DESC
            LIMIT ? OFFSET ?
        """, params + [page_size, offset])

        rows = cursor.fetchall()

        # 转换为字典列表
        records = []
        for row in rows:
            records.append({
                "id": row[0],
                "business_id": row[1],
                "doc_number": row[2],
                "doc_type": row[3],
                "product_type": row[4],
                "file_name": row[5],
                "file_size": row[6],
                "upload_time": row[7],
                "status": row[8],
                "error_code": row[9],
                "error_message": row[10],
                "checked": bool(row[11]),  # SQLite INTEGER转Python布尔值
                "notes": row[12]  # 新增备注字段
            })

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "records": records
        }


@router.get("/export")
async def export_records(
    search: Optional[str] = Query(None, description="搜索关键词"),
    doc_type: Optional[str] = Query(None, description="单据类型筛选"),
    product_type: Optional[str] = Query(None, description="产品类型筛选"),
    status: Optional[str] = Query(None, description="状态筛选"),
    start_date: Optional[str] = Query(None, description="开始日期"),
    end_date: Optional[str] = Query(None, description="结束日期")
):
    """
    导出上传记录为ZIP包（包含Excel表格和所有图片文件）

    查询参数: 与/records接口相同（不包含分页参数）

    响应: ZIP文件流
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # 构建WHERE条件（移除硬编码的status过滤，支持动态筛选）
        where_clauses = ["deleted_at IS NULL"]
        params = []

        if search:
            where_clauses.append("(doc_number LIKE ? OR file_name LIKE ?)")
            search_pattern = f"%{search}%"
            params.extend([search_pattern, search_pattern])

        if doc_type:
            where_clauses.append("doc_type = ?")
            params.append(doc_type)

        if product_type:
            where_clauses.append("product_type = ?")
            params.append(product_type)

        if status:
            where_clauses.append("status = ?")
            params.append(status)

        if start_date:
            where_clauses.append("DATE(upload_time) >= ?")
            params.append(start_date)

        if end_date:
            where_clauses.append("DATE(upload_time) <= ?")
            params.append(end_date)

        where_sql = " AND ".join(where_clauses)

        # 查询所有匹配记录（包括status、local_file_path和notes）
        cursor.execute(f"""
            SELECT doc_number, doc_type, product_type, business_id, upload_time, file_name,
                   file_size, status, local_file_path, notes
            FROM upload_history
            WHERE {where_sql}
            ORDER BY upload_time DESC
        """, params)

        rows = cursor.fetchall()

    # 创建临时目录和ZIP文件
    temp_dir = tempfile.mkdtemp()
    timestamp = get_beijing_now_naive().strftime('%Y%m%d_%H%M%S')
    zip_filename = f"upload_records_{timestamp}.zip"
    zip_path = os.path.join(temp_dir, zip_filename)

    try:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # 生成Excel文件
            wb = Workbook()
            ws = wb.active
            ws.title = "上传记录"

            # 写入表头（新增"状态"和"备注"列）
            headers = ["单据编号", "单据类型", "产品类型", "业务ID", "上传时间", "文件名", "文件大小(字节)", "状态", "备注"]
            ws.append(headers)

            # 写入数据并收集图片文件
            for row in rows:
                doc_number, doc_type, product_type, business_id, upload_time, file_name, file_size, status, local_file_path, notes = row
                ws.append([doc_number, doc_type, product_type or '', business_id, upload_time, file_name, file_size, status, notes or ''])

                # 添加本地图片文件到ZIP（所有状态的记录，只要文件存在就添加）
                if local_file_path and os.path.exists(local_file_path):
                    # 在ZIP中使用相对路径：images/文件名
                    arcname = os.path.join("images", os.path.basename(local_file_path))
                    zipf.write(local_file_path, arcname=arcname)

            # 保存Excel到临时文件
            excel_temp_path = os.path.join(temp_dir, f"upload_records_{timestamp}.xlsx")
            wb.save(excel_temp_path)

            # 添加Excel文件到ZIP
            zipf.write(excel_temp_path, arcname=f"upload_records_{timestamp}.xlsx")

        # 返回ZIP文件
        return FileResponse(
            path=zip_path,
            media_type="application/zip",
            filename=zip_filename,
            background=None  # 文件下载后不自动删除，需要手动清理
        )

    except Exception as e:
        # 清理临时文件
        if os.path.exists(zip_path):
            os.remove(zip_path)
        if os.path.exists(temp_dir):
            os.rmdir(temp_dir)
        raise HTTPException(status_code=500, detail=f"导出失败: {str(e)}")


@router.get("/statistics")
async def get_statistics() -> Dict[str, Any]:
    """
    获取统计数据

    响应格式:
    {
        "total_uploads": 1500,
        "pending_count": 10,
        "uploading_count": 5,
        "success_count": 1450,
        "failed_count": 35,
        "by_doc_type": {
            "销售": 800,
            "转库": 600,
            "其他": 100
        }
    }
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # 总上传数和各状态数量（只统计未删除的记录）
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
                SUM(CASE WHEN status = 'uploading' THEN 1 ELSE 0 END) as uploading,
                SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed
            FROM upload_history
            WHERE deleted_at IS NULL
        """)
        row = cursor.fetchone()
        total_uploads = row[0]
        pending_count = row[1] or 0
        uploading_count = row[2] or 0
        success_count = row[3] or 0
        failed_count = row[4] or 0

        # 按单据类型统计（只统计未删除的记录）
        cursor.execute("""
            SELECT doc_type, COUNT(*) as count
            FROM upload_history
            WHERE doc_type IS NOT NULL AND deleted_at IS NULL
            GROUP BY doc_type
        """)

        by_doc_type = {}
        for row in cursor.fetchall():
            by_doc_type[row[0]] = row[1]

        return {
            "total_uploads": total_uploads,
            "pending_count": pending_count,
            "uploading_count": uploading_count,
            "success_count": success_count,
            "failed_count": failed_count,
            "by_doc_type": by_doc_type
        }


class DeleteRecordsRequest(BaseModel):
    """删除记录请求模型"""
    ids: List[int]


class UpdateCheckStatusRequest(BaseModel):
    """更新检查状态请求模型"""
    checked: bool

    class Config:
        schema_extra = {
            "example": {
                "checked": True
            }
        }


@router.delete("/records")
async def delete_records(request: DeleteRecordsRequest) -> Dict[str, Any]:
    """
    软删除上传记录（批量）

    请求体:
    {
        "ids": [1, 2, 3]  // 要删除的记录ID列表
    }

    响应格式:
    {
        "success": true,
        "deleted_count": 3,
        "message": "成功删除3条记录"
    }

    说明:
    - 采用软删除策略，只标记deleted_at字段，不物理删除数据
    - 不删除本地文件系统的文件
    - 幂等性设计：重复删除已删除的记录不报错
    - 不调用用友云API
    """
    if not request.ids:
        raise HTTPException(status_code=400, detail="请至少选择一条记录")

    # 验证所有ID为正整数
    if any(id <= 0 for id in request.ids):
        raise HTTPException(status_code=400, detail="无效的记录ID")

    with get_db_connection() as conn:
        cursor = conn.cursor()

        try:
            # 构建IN子句的占位符
            placeholders = ','.join('?' * len(request.ids))

            # 软删除：设置deleted_at字段为当前时间（北京时间）
            current_time = get_beijing_now_naive().isoformat()
            cursor.execute(f"""
                UPDATE upload_history
                SET deleted_at = ?
                WHERE id IN ({placeholders})
                AND deleted_at IS NULL
            """, [current_time] + request.ids)

            deleted_count = cursor.rowcount
            conn.commit()

            return {
                "success": True,
                "deleted_count": deleted_count,
                "message": f"成功删除{deleted_count}条记录"
            }

        except Exception as e:
            conn.rollback()
            raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")


@router.patch("/records/{record_id}/check")
async def update_check_status(
    record_id: int,
    request: UpdateCheckStatusRequest
) -> Dict[str, Any]:
    """
    更新记录的检查状态

    路径参数:
    - record_id: 记录ID

    请求体:
    {
        "checked": true/false  // 检查状态
    }

    响应格式:
    {
        "success": true,
        "id": 123,
        "checked": true,
        "message": "检查状态已更新"
    }

    错误响应:
    - 404: 记录不存在或已删除
    - 422: 请求参数错误
    - 500: 服务器内部错误
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()

        try:
            # 检查记录是否存在(且未被软删除)
            cursor.execute("""
                SELECT id FROM upload_history
                WHERE id = ? AND deleted_at IS NULL
            """, [record_id])

            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="记录不存在或已删除")

            # 更新检查状态(SQLite使用0/1表示布尔值)
            checked_value = 1 if request.checked else 0
            current_time = get_beijing_now_naive().isoformat()

            cursor.execute("""
                UPDATE upload_history
                SET checked = ?, updated_at = ?
                WHERE id = ?
            """, [checked_value, current_time, record_id])

            conn.commit()

            return {
                "success": True,
                "id": record_id,
                "checked": request.checked,
                "message": "检查状态已更新"
            }

        except HTTPException:
            # 重新抛出HTTP异常
            raise
        except Exception as e:
            conn.rollback()
            raise HTTPException(status_code=500, detail=f"更新失败: {str(e)}")


class UpdateNotesRequest(BaseModel):
    """更新备注请求模型"""
    notes: str

    class Config:
        schema_extra = {
            "example": {
                "notes": "这是备注内容"
            }
        }


@router.patch("/records/{record_id}/notes")
async def update_notes(
    record_id: int,
    request: UpdateNotesRequest
) -> Dict[str, Any]:
    """
    更新记录的备注内容

    路径参数:
    - record_id: 记录ID

    请求体:
    {
        "notes": "备注内容"  // 最大1000字符
    }

    响应格式:
    {
        "success": true,
        "id": 123,
        "notes": "备注内容",
        "message": "备注已更新"
    }

    错误响应:
    - 400: 备注内容超过1000字符
    - 404: 记录不存在或已删除
    - 500: 服务器内部错误
    """
    # 验证备注长度
    if len(request.notes) > 1000:
        raise HTTPException(status_code=400, detail="备注内容不能超过1000字符")

    with get_db_connection() as conn:
        cursor = conn.cursor()

        try:
            # 检查记录是否存在(且未被软删除)
            cursor.execute("""
                SELECT id FROM upload_history
                WHERE id = ? AND deleted_at IS NULL
            """, [record_id])

            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="记录不存在或已删除")

            # 更新备注内容（空字符串转为NULL）
            current_time = get_beijing_now_naive().isoformat()
            notes_value = request.notes.strip() if request.notes.strip() else None

            cursor.execute("""
                UPDATE upload_history
                SET notes = ?, updated_at = ?
                WHERE id = ?
            """, [notes_value, current_time, record_id])

            conn.commit()

            return {
                "success": True,
                "id": record_id,
                "notes": notes_value,
                "message": "备注已更新"
            }

        except HTTPException:
            # 重新抛出HTTP异常
            raise
        except Exception as e:
            conn.rollback()
            raise HTTPException(status_code=500, detail=f"更新失败: {str(e)}")


@router.get("/files/{record_id}/preview")
async def preview_file(record_id: int):
    """
    预览文件（返回图片用于浏览器直接显示）

    路径参数:
    - record_id: 记录ID

    响应:
    - 200: 返回图片文件内容（浏览器直接显示）
    - 404: 记录不存在、已删除或文件不存在
    - 500: 服务器错误

    支持的图片格式: jpg, jpeg, png, gif, bmp, webp
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()

        try:
            # 查询文件路径和扩展名
            cursor.execute("""
                SELECT local_file_path, file_extension, file_name
                FROM upload_history
                WHERE id = ? AND deleted_at IS NULL
            """, [record_id])

            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="记录不存在或已删除")

            local_file_path, file_extension, file_name = row

            # 检查文件是否存在
            if not local_file_path or not os.path.exists(local_file_path):
                raise HTTPException(status_code=404, detail="文件不存在")

            # 根据文件扩展名确定 MIME 类型
            extension_to_mime = {
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
                ".gif": "image/gif",
                ".bmp": "image/bmp",
                ".webp": "image/webp"
            }
            media_type = extension_to_mime.get(file_extension.lower(), "application/octet-stream")

            # 返回文件用于预览（浏览器直接显示）
            return FileResponse(
                path=local_file_path,
                media_type=media_type,
                filename=file_name
            )

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"预览失败: {str(e)}")


@router.get("/files/{record_id}/download")
async def download_file(record_id: int):
    """
    下载单个文件

    路径参数:
    - record_id: 记录ID

    响应:
    - 200: 返回文件下载流（触发浏览器下载）
    - 404: 记录不存在、已删除或文件不存在
    - 500: 服务器错误
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()

        try:
            # 查询文件路径和文件名
            cursor.execute("""
                SELECT local_file_path, file_name
                FROM upload_history
                WHERE id = ? AND deleted_at IS NULL
            """, [record_id])

            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="记录不存在或已删除")

            local_file_path, file_name = row

            # 检查文件是否存在
            if not local_file_path or not os.path.exists(local_file_path):
                raise HTTPException(status_code=404, detail="文件不存在")

            # 返回文件下载（浏览器触发下载）
            return FileResponse(
                path=local_file_path,
                media_type="application/octet-stream",
                filename=file_name,
                headers={"Content-Disposition": f'attachment; filename="{file_name}"'}
            )

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"下载失败: {str(e)}")
