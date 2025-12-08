from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from starlette.background import BackgroundTask
from typing import List, Dict, Any, Optional
from datetime import datetime
import asyncio
import time
from pydantic import BaseModel
import csv
import io
import os
import zipfile
import tempfile
import shutil
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
    end_date: Optional[str] = Query(None, description="结束日期（YYYY-MM-DD）"),
    logistics: Optional[str] = Query(None, description="物流公司筛选")
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
    - logistics: 物流公司筛选（'全部物流'表示不过滤）

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

        if logistics and logistics != "全部物流":
            where_clauses.append("logistics = ?")
            params.append(logistics)

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
                   upload_time, status, error_code, error_message, checked, notes, logistics
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
                "notes": row[12],  # 新增备注字段
                "logistics": row[13]
            })

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "records": records
        }




@router.get("/logistics-options")
async def get_logistics_options() -> Dict[str, List[str]]:
    """获取可选的物流公司列表(含默认'全部物流')

    Returns:
        包含logistics_list的字典
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT logistics
            FROM upload_history
            WHERE logistics IS NOT NULL AND logistics != ''
            ORDER BY logistics ASC
        """)
        rows = cursor.fetchall()

    logistics_list = ["全部物流"]
    logistics_list.extend([row[0] for row in rows if row[0]])

    return {"logistics_list": logistics_list}


@router.get("/export")
async def export_records(
    search: Optional[str] = Query(None, description="搜索关键词"),
    doc_type: Optional[str] = Query(None, description="单据类型筛选"),
    product_type: Optional[str] = Query(None, description="产品类型筛选"),
    status: Optional[str] = Query(None, description="状态筛选"),
    start_date: Optional[str] = Query(None, description="开始日期"),
    end_date: Optional[str] = Query(None, description="结束日期"),
    logistics: Optional[str] = Query(None, description="物流公司筛选"),
    include_excel: bool = Query(True, description="是否包含Excel数据"),
    include_images: bool = Query(True, description="是否包含图片文件")
):
    """
    导出上传记录，支持选择性导出Excel和/或图片

    响应:
    - Both: ZIP文件 (Excel + images/)
    - Excel only: 直接.xlsx文件
    - Images only: ZIP文件 (仅images/)
    """
    import logging
    from app.core.file_manager import FileManager

    logger = logging.getLogger(__name__)
    file_manager = None
    temp_dir: Optional[str] = None

    # 参数校验: 至少需要选择一项
    if not include_excel and not include_images:
        raise HTTPException(
            status_code=400,
            detail="至少选择一项导出内容 (include_excel 或 include_images)"
        )

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            # 构建WHERE条件
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

            if logistics and logistics != "全部物流":
                where_clauses.append("logistics = ?")
                params.append(logistics)

            where_sql = " AND ".join(where_clauses)

            # 动态检测webdav_path字段是否存在（兼容未完成迁移的旧数据库）
            cursor.execute("PRAGMA table_info(upload_history)")
            columns = {col[1] for col in cursor.fetchall()}
            has_webdav_path = "webdav_path" in columns
            webdav_select = "webdav_path" if has_webdav_path else "NULL as webdav_path"

            cursor.execute(f"""
                SELECT doc_number, doc_type, product_type, business_id, upload_time, file_name,
                       file_size, status, local_file_path, notes, {webdav_select}
                FROM upload_history
                WHERE {where_sql}
                ORDER BY upload_time DESC
            """, params)

            rows = cursor.fetchall()

        logger.info(f"[导出] 查询到 {len(rows)} 条记录, include_excel={include_excel}, include_images={include_images}")

        temp_dir = tempfile.mkdtemp()
        timestamp = get_beijing_now_naive().strftime('%Y%m%d_%H%M%S')
        is_empty = len(rows) == 0

        # 生成Excel
        excel_path = None
        if include_excel:
            wb = Workbook()
            ws = wb.active
            ws.title = "上传记录"
            headers = ["单据编号", "单据类型", "产品类型", "业务ID", "上传时间", "文件名", "文件大小(字节)", "状态", "备注"]
            ws.append(headers)

            for row in rows:
                doc_number, doc_type_val, product_type_val, business_id, upload_time, file_name, file_size, status_val, local_file_path, notes, webdav_path = row
                ws.append([doc_number, doc_type_val, product_type_val or '', business_id, upload_time, file_name, file_size, status_val, notes or ''])

            excel_filename = f"upload_records_{timestamp}.xlsx"
            excel_path = os.path.join(temp_dir, excel_filename)
            wb.save(excel_path)
            logger.info(f"[导出] Excel生成完成: {excel_filename}")

        # 收集图片文件
        image_files = []
        if include_images:
            for row in rows:
                doc_number, doc_type_val, product_type_val, business_id, upload_time, file_name, file_size, status_val, local_file_path, notes, webdav_path = row
                arcname = os.path.join("images", file_name or f"{business_id}_{doc_number or 'unknown'}")
                local_exists = local_file_path and os.path.exists(local_file_path)

                if local_exists:
                    image_files.append({
                        "arcname": arcname,
                        "local_path": local_file_path,
                        "webdav_path": None,
                        "doc_number": doc_number,
                        "business_id": business_id
                    })
                elif webdav_path:
                    image_files.append({
                        "arcname": arcname,
                        "local_path": None,
                        "webdav_path": webdav_path,
                        "doc_number": doc_number,
                        "business_id": business_id
                    })
                else:
                    logger.debug(f"[导出] 记录无可用图片 doc_number={doc_number} business_id={business_id}")

        # 构建响应
        if include_excel and include_images:
            zip_filename = f"upload_records_{timestamp}.zip"
            zip_path = os.path.join(temp_dir, zip_filename)

            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                zipf.write(excel_path, arcname=f"upload_records_{timestamp}.xlsx")

                image_local_count, image_webdav_count, image_missing_count = await _add_images_to_zip(
                    zipf, image_files, file_manager, logger
                )

                if image_local_count == 0 and image_webdav_count == 0:
                    zipf.writestr(zipfile.ZipInfo("images/"), b"")

            logger.info(f"[导出] ZIP打包完成: {zip_filename}")

            response = FileResponse(
                path=zip_path,
                media_type="application/zip",
                filename=zip_filename,
                background=BackgroundTask(shutil.rmtree, temp_dir, ignore_errors=True)
            )
            if is_empty:
                response.headers["X-Export-Empty"] = "true"
            return response

        if include_excel and not include_images:
            response = FileResponse(
                path=excel_path,
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                filename=f"upload_records_{timestamp}.xlsx",
                background=BackgroundTask(shutil.rmtree, temp_dir, ignore_errors=True)
            )
            if is_empty:
                response.headers["X-Export-Empty"] = "true"
            return response

        if not include_excel and include_images:
            zip_filename = f"images_{timestamp}.zip"
            zip_path = os.path.join(temp_dir, zip_filename)

            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                image_local_count, image_webdav_count, image_missing_count = await _add_images_to_zip(
                    zipf, image_files, file_manager, logger
                )

                if image_local_count == 0 and image_webdav_count == 0:
                    zipf.writestr(zipfile.ZipInfo("images/"), b"")

            logger.info(
                f"[导出] 图片ZIP打包完成: {zip_filename}, 本地={image_local_count}, WebDAV={image_webdav_count}, 缺失={image_missing_count}"
            )

            response = FileResponse(
                path=zip_path,
                media_type="application/zip",
                filename=zip_filename,
                background=BackgroundTask(shutil.rmtree, temp_dir, ignore_errors=True)
            )
            if is_empty or (image_local_count == 0 and image_webdav_count == 0):
                response.headers["X-Export-Empty"] = "true"
            return response

    except HTTPException:
        # 不吞掉明确的HTTP错误
        raise
    except Exception as e:
        logger.error(f"[导出] 导出失败: {str(e)}", exc_info=True)
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)

        if "Excel" in str(e) or "Workbook" in str(e):
            raise HTTPException(status_code=500, detail="Excel文件生成失败")
        if "ZIP" in str(e) or "zipfile" in str(e):
            raise HTTPException(status_code=500, detail="压缩文件创建失败")
        raise HTTPException(status_code=500, detail=f"导出失败: {str(e)}")


async def _add_images_to_zip(zipf, image_files, file_manager, logger):
    """将图片添加到ZIP的辅助函数，支持本地文件和WebDAV下载"""
    from app.core.file_manager import FileManager

    image_local_count = 0
    image_webdav_count = 0
    image_missing_count = 0
    download_jobs = []

    for img in image_files:
        if img["local_path"]:
            try:
                zipf.write(img["local_path"], arcname=img["arcname"])
                image_local_count += 1
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[导出] 本地图片添加失败: {img['arcname']}, 错误: {e}")
                image_missing_count += 1
        elif img["webdav_path"]:
            download_jobs.append(img)
        else:
            image_missing_count += 1

    if download_jobs:
        if file_manager is None:
            file_manager = FileManager()

        concurrency_limit = 15
        semaphore = asyncio.Semaphore(concurrency_limit)

        async def download_and_write(job):
            async with semaphore:
                try:
                    file_content = await file_manager.get_file(job["webdav_path"])
                    zipf.writestr(job["arcname"], file_content)
                    return True
                except Exception as e:  # noqa: BLE001
                    logger.warning(
                        f"[导出] WebDAV图片获取失败 doc_number={job['doc_number']} "
                        f"webdav_path={job['webdav_path']} 错误={str(e)}"
                    )
                    return False

        results = await asyncio.gather(*(download_and_write(job) for job in download_jobs))
        webdav_success = sum(1 for r in results if r)
        webdav_failed = len(results) - webdav_success
        image_webdav_count += webdav_success
        image_missing_count += webdav_failed

    return image_local_count, image_webdav_count, image_missing_count


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

    文件获取策略:
    1. 优先从本地文件路径读取(旧数据)
    2. 如果本地文件不存在,尝试从WebDAV缓存读取(新数据)
    3. 如果缓存也不存在,从WebDAV下载并缓存
    """
    import logging
    import time
    from app.core.file_manager import FileManager
    from fastapi.responses import Response

    logger = logging.getLogger(__name__)
    file_manager = FileManager()

    # 性能监控 - 开始计时
    start_time = time.time()
    access_method = "unknown"  # 文件访问方式: local/cache/webdav

    with get_db_connection() as conn:
        cursor = conn.cursor()

        try:
            # 查询文件路径和扩展名
            cursor.execute("""
                SELECT local_file_path, file_extension, file_name, webdav_path
                FROM upload_history
                WHERE id = ? AND deleted_at IS NULL
            """, [record_id])

            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="记录不存在或已删除")

            local_file_path, file_extension, file_name, webdav_path = row

            # 根据文件扩展名确定 MIME 类型
            extension_to_mime = {
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
                ".gif": "image/gif",
                ".bmp": "image/bmp",
                ".webp": "image/webp"
            }
            media_type = extension_to_mime.get(file_extension.lower() if file_extension else "", "application/octet-stream")

            # 策略1: 优先检查本地文件是否存在
            if local_file_path and os.path.exists(local_file_path):
                access_method = "local"
                elapsed_time = (time.time() - start_time) * 1000  # 转换为毫秒
                logger.info(f"[性能] 预览文件 record_id={record_id} 方式=本地文件 耗时={elapsed_time:.2f}ms")

                return FileResponse(
                    path=local_file_path,
                    media_type=media_type,
                    filename=file_name
                )

            # 策略2: 如果有webdav_path,尝试从WebDAV获取
            if webdav_path:
                try:
                    # 检查是否是缓存命中
                    cache_path = file_manager._get_cache_path(webdav_path)
                    is_cache_hit = file_manager._is_cache_valid(cache_path)
                    access_method = "cache" if is_cache_hit else "webdav"

                    # 从WebDAV获取文件(会自动尝试缓存)
                    file_content = await file_manager.get_file(webdav_path)

                    elapsed_time = (time.time() - start_time) * 1000
                    logger.info(f"[性能] 预览文件 record_id={record_id} 方式={access_method} 耗时={elapsed_time:.2f}ms")

                    return Response(
                        content=file_content,
                        media_type=media_type,
                        headers={
                            "Content-Disposition": f'inline; filename="{file_name}"',
                            "Cache-Control": "public, max-age=3600"
                        }
                    )
                except Exception as e:
                    # WebDAV获取失败,记录日志但继续尝试其他方式
                    elapsed_time = (time.time() - start_time) * 1000
                    logger.warning(f"[性能] 预览文件失败 record_id={record_id} 方式={access_method} 耗时={elapsed_time:.2f}ms 错误={str(e)}")

            # 策略3: 都失败了,返回404
            raise HTTPException(status_code=404, detail="文件不存在或无法访问")

        except HTTPException:
            raise
        except Exception as e:
            elapsed_time = (time.time() - start_time) * 1000
            logger.error(f"[性能] 预览失败 record_id={record_id} 耗时={elapsed_time:.2f}ms 错误={str(e)}")
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

    文件获取策略:
    1. 优先从本地文件路径读取(旧数据)
    2. 如果本地文件不存在,尝试从WebDAV获取(新数据)
    """
    import logging
    import time
    from app.core.file_manager import FileManager
    from fastapi.responses import Response

    logger = logging.getLogger(__name__)
    file_manager = FileManager()

    # 性能监控 - 开始计时
    start_time = time.time()
    access_method = "unknown"  # 文件访问方式: local/cache/webdav

    with get_db_connection() as conn:
        cursor = conn.cursor()

        try:
            # 查询文件路径和文件名
            cursor.execute("""
                SELECT local_file_path, file_name, webdav_path
                FROM upload_history
                WHERE id = ? AND deleted_at IS NULL
            """, [record_id])

            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="记录不存在或已删除")

            local_file_path, file_name, webdav_path = row

            # 策略1: 优先检查本地文件是否存在
            if local_file_path and os.path.exists(local_file_path):
                access_method = "local"
                elapsed_time = (time.time() - start_time) * 1000  # 转换为毫秒
                logger.info(f"[性能] 下载文件 record_id={record_id} 方式=本地文件 耗时={elapsed_time:.2f}ms")

                return FileResponse(
                    path=local_file_path,
                    media_type="application/octet-stream",
                    filename=file_name,
                    headers={"Content-Disposition": f'attachment; filename="{file_name}"'}
                )

            # 策略2: 如果有webdav_path,尝试从WebDAV获取
            if webdav_path:
                try:
                    # 检查是否是缓存命中
                    cache_path = file_manager._get_cache_path(webdav_path)
                    is_cache_hit = file_manager._is_cache_valid(cache_path)
                    access_method = "cache" if is_cache_hit else "webdav"

                    # 从WebDAV获取文件
                    file_content = await file_manager.get_file(webdav_path)

                    elapsed_time = (time.time() - start_time) * 1000
                    logger.info(f"[性能] 下载文件 record_id={record_id} 方式={access_method} 耗时={elapsed_time:.2f}ms")

                    return Response(
                        content=file_content,
                        media_type="application/octet-stream",
                        headers={
                            "Content-Disposition": f'attachment; filename="{file_name}"'
                        }
                    )
                except Exception as e:
                    # WebDAV获取失败,记录日志
                    elapsed_time = (time.time() - start_time) * 1000
                    logger.warning(f"[性能] 下载文件失败 record_id={record_id} 方式={access_method} 耗时={elapsed_time:.2f}ms 错误={str(e)}")

            # 策略3: 都失败了,返回404
            raise HTTPException(status_code=404, detail="文件不存在或无法访问")

        except HTTPException:
            raise
        except Exception as e:
            elapsed_time = (time.time() - start_time) * 1000
            logger.error(f"[性能] 下载失败 record_id={record_id} 耗时={elapsed_time:.2f}ms 错误={str(e)}")
            raise HTTPException(status_code=500, detail=f"下载失败: {str(e)}")
