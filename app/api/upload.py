from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks
from typing import List, Optional
import asyncio
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from app.core.config import get_settings
from app.core.yonyou_client import YonYouClient
from app.core.database import get_db_connection
from app.core.file_manager import FileManager
from app.core.timezone import get_beijing_now_naive
from app.models.upload_history import UploadHistory

router = APIRouter()
settings = get_settings()
yonyou_client = YonYouClient()
file_manager = FileManager()

# doc_type到businessType的映射常量
DOC_TYPE_TO_BUSINESS_TYPE = {
    "销售": "yonbip-scm-scmsa",
    "转库": "yonbip-scm-stock",
    "其他": "yonbip-scm-stock"
}


def generate_unique_filename(doc_number: str, file_extension: str, storage_path: str) -> tuple[str, str]:
    """
    生成唯一的文件名（并发安全）

    使用 UUID4 + 时间戳 的组合确保文件名唯一性，避免并发上传时的命名冲突。

    文件名格式: {doc_number}_{timestamp}_{uuid_short}{extension}
    示例: SO20250103001_20251020143025_a3f2b1c4.jpg

    Args:
        doc_number: 单据编号
        file_extension: 文件扩展名（如.jpg）
        storage_path: 存储路径

    Returns:
        tuple: (新文件名, 完整路径)
    """
    # 获取当前时间戳（精确到秒）
    timestamp = get_beijing_now_naive().strftime("%Y%m%d%H%M%S")

    # 生成8位短UUID（UUID4的前8个字符，已足够避免冲突）
    short_uuid = str(uuid.uuid4()).replace('-', '')[:8]

    # 构造文件名: 单据号_时间戳_短UUID.扩展名
    new_filename = f"{doc_number}_{timestamp}_{short_uuid}{file_extension}"
    full_path = os.path.join(storage_path, new_filename)

    return new_filename, full_path


def save_file_locally(file_content: bytes, file_path: str) -> None:
    """
    保存文件到本地

    Args:
        file_content: 文件内容
        file_path: 完整文件路径
    """
    # 确保目录存在
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    # 保存文件
    with open(file_path, 'wb') as f:
        f.write(file_content)


async def background_upload_to_yonyou(
    file_content: bytes,
    new_filename: str,
    business_id: str,
    business_type: str,
    local_file_path: str,
    record_id: int
):
    """
    后台任务：上传文件到WebDAV + 用友云并更新数据库状态

    Args:
        file_content: 文件二进制内容
        new_filename: 新文件名
        business_id: 业务单据ID
        business_type: 业务类型
        local_file_path: 本地文件路径
        record_id: 数据库记录ID
    """
    from app.core.timezone import get_beijing_now_naive

    conn = None
    webdav_result = None

    try:
        # 更新状态为 uploading (使用并发安全的数据库连接)
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE upload_history
                SET status = 'uploading', updated_at = ?
                WHERE id = ?
            """, (get_beijing_now_naive().isoformat(), record_id))
            conn.commit()
    except Exception as e:
        print(f"更新uploading状态失败: {str(e)}")
        # 继续执行上传，即使状态更新失败

    conn = None
    try:
        # 1. 保存到WebDAV + 本地缓存
        try:
            webdav_result = await file_manager.save_file(file_content, new_filename)
            if webdav_result['success']:
                print(f"WebDAV保存成功: {webdav_result['webdav_path']}")
            else:
                print(f"WebDAV保存失败: {webdav_result.get('error', '未知错误')}")
        except Exception as e:
            print(f"WebDAV保存异常: {str(e)}")
            webdav_result = {'success': False, 'error': str(e)}

        # 2. 保存到本地作为备份（如果WebDAV失败）
        if not webdav_result.get('success') and local_file_path:
            try:
                save_file_locally(file_content, local_file_path)
                print(f"本地备份保存成功: {local_file_path}")
            except Exception as e:
                print(f"本地备份保存失败: {str(e)}")

        # 3. 上传到用友云（保持现有重试机制）
        yonyou_file_id = None
        error_code = None
        error_message = None
        retry_count = 0

        for attempt in range(settings.MAX_RETRY_COUNT):
            result = await yonyou_client.upload_file(
                file_content,
                new_filename,
                business_id,
                retry_count=attempt,
                business_type=business_type
            )

            if result["success"]:
                yonyou_file_id = result["data"]["id"]
                retry_count = attempt
                break
            else:
                error_code = result["error_code"]
                error_message = result["error_message"]
                retry_count = attempt + 1

                if attempt < settings.MAX_RETRY_COUNT - 1:
                    await asyncio.sleep(settings.RETRY_DELAY)

        # 4. 更新最终状态 (使用并发安全的数据库连接)
        with get_db_connection() as conn:
            cursor = conn.cursor()

            # 计算缓存过期时间
            cache_expiry_time = None
            if webdav_result.get('success') and webdav_result.get('is_cached'):
                cache_expiry_time = (get_beijing_now_naive() + timedelta(days=settings.CACHE_DAYS)).isoformat()

            if yonyou_file_id:
                # 用友云上传成功
                cursor.execute("""
                    UPDATE upload_history
                    SET status = 'success',
                        yonyou_file_id = ?,
                        webdav_path = ?,
                        is_cached = ?,
                        cache_expiry_time = ?,
                        retry_count = ?,
                        updated_at = ?
                    WHERE id = ?
                """, (
                    yonyou_file_id,
                    webdav_result.get('webdav_path') if webdav_result else None,
                    webdav_result.get('is_cached', False) if webdav_result else False,
                    cache_expiry_time,
                    retry_count,
                    get_beijing_now_naive().isoformat(),
                    record_id
                ))
            else:
                # 用友云上传失败
                cursor.execute("""
                    UPDATE upload_history
                    SET status = 'failed',
                        error_code = ?,
                        error_message = ?,
                        webdav_path = ?,
                        is_cached = ?,
                        cache_expiry_time = ?,
                        retry_count = ?,
                        updated_at = ?
                    WHERE id = ?
                """, (
                    error_code,
                    error_message,
                    webdav_result.get('webdav_path') if webdav_result else None,
                    webdav_result.get('is_cached', False) if webdav_result else False,
                    cache_expiry_time,
                    retry_count,
                    get_beijing_now_naive().isoformat(),
                    record_id
                ))

            conn.commit()

            # 5. 如果WebDAV保存成功，插入文件元数据记录
            if webdav_result and webdav_result.get('success'):
                try:
                    cursor.execute("""
                        INSERT INTO file_metadata
                        (filename, webdav_path, local_cache_path, upload_time, file_size,
                         is_cached, last_access_time, webdav_etag, is_synced, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        new_filename,
                        webdav_result.get('webdav_path'),
                        webdav_result.get('local_cache_path'),
                        webdav_result.get('upload_time'),
                        webdav_result.get('file_size'),
                        webdav_result.get('is_cached', False),
                        get_beijing_now_naive().isoformat(),
                        webdav_result.get('webdav_etag'),
                        webdav_result.get('is_synced', False),
                        get_beijing_now_naive().isoformat(),
                        get_beijing_now_naive().isoformat()
                    ))
                    conn.commit()
                except Exception as e:
                    print(f"插入文件元数据失败: {str(e)}")

    except Exception as e:
        # 异常处理：标记为失败 (使用并发安全的数据库连接)
        print(f"后台上传任务异常: {str(e)}")
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE upload_history
                    SET status = 'failed',
                        error_code = 'BACKGROUND_TASK_ERROR',
                        error_message = ?,
                        updated_at = ?
                    WHERE id = ?
                """, (str(e), get_beijing_now_naive().isoformat(), record_id))
                conn.commit()
        except Exception as inner_e:
            print(f"更新失败状态时出错: {str(inner_e)}")


@router.post("/upload")
async def upload_files(
    background_tasks: BackgroundTasks,
    business_id: str = Form(..., description="业务单据ID"),
    doc_number: str = Form(..., description="单据编号"),
    doc_type: str = Form(..., description="单据类型"),
    product_type: Optional[str] = Form(None, description="产品类型(如:油脂/快消)"),
    files: List[UploadFile] = File(...)
):
    """
    批量上传文件（异步处理）

    流程优化：
    1. 前端上传文件到后端
    2. 后端立即保存记录到数据库（状态：pending）
    3. 立即返回成功响应（< 1秒）
    4. 后台任务异步上传到用友云
    5. 上传完成后更新数据库状态（success/failed）

    请求参数:
    - business_id: 业务单据ID（纯数字，用于用友云API）
    - doc_number: 单据编号（业务标识，如SO20250103001）
    - doc_type: 单据类型（销售/转库/其他）
    - product_type: 产品类型（可选）
    - files: 文件列表 (最多10个)

    响应格式:
    {
        "success": true,
        "total": 10,
        "message": "已接收10个文件，正在后台上传中",
        "records": [
            {
                "id": 123,
                "file_name": "SO001_20251021_a3f2b1c4.jpg",
                "original_name": "photo.jpg",
                "status": "pending",
                "file_size": 102400
            }
        ]
    }
    """
    # 验证businessId格式
    if not business_id or not business_id.isdigit():
        raise HTTPException(status_code=400, detail="businessId必须为纯数字")

    # 验证doc_type枚举值
    valid_doc_types = ["销售", "转库", "其他"]
    if doc_type not in valid_doc_types:
        raise HTTPException(
            status_code=400,
            detail=f"doc_type必须为以下值之一: {', '.join(valid_doc_types)}"
        )

    # 获取映射后的businessType
    business_type = DOC_TYPE_TO_BUSINESS_TYPE.get(doc_type, settings.YONYOU_BUSINESS_TYPE)

    # 验证文件数量
    if len(files) > settings.MAX_FILES_PER_REQUEST:
        raise HTTPException(status_code=400, detail=f"单次最多上传{settings.MAX_FILES_PER_REQUEST}个文件")

    # 验证文件
    for file in files:
        # 检查文件扩展名
        file_ext = "." + file.filename.split(".")[-1].lower()
        if file_ext not in settings.ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的文件格式: {file_ext}，支持的格式: {', '.join(settings.ALLOWED_EXTENSIONS)}"
            )

    # 处理每个文件（快速保存记录，添加后台任务）
    records = []
    from app.core.timezone import get_beijing_now_naive

    for upload_file in files:
        # 读取文件内容
        file_content = await upload_file.read()
        file_size = len(file_content)

        # 验证文件大小
        if file_size > settings.MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"文件 {upload_file.filename} 大小超过{settings.MAX_FILE_SIZE / 1024 / 1024}MB限制"
            )

        # 获取文件扩展名
        file_extension = "." + upload_file.filename.split(".")[-1].lower()

        # 生成唯一文件名
        storage_path = settings.LOCAL_STORAGE_PATH
        new_filename, local_file_path = generate_unique_filename(
            doc_number, file_extension, storage_path
        )

        # 立即保存记录到数据库（状态：pending，使用并发安全的数据库连接）
        with get_db_connection() as conn:
            cursor = conn.cursor()

            beijing_now = get_beijing_now_naive()
            upload_time_str = beijing_now.isoformat()

            cursor.execute("""
                INSERT INTO upload_history
                (business_id, doc_number, doc_type, product_type, file_name, file_size, file_extension,
                 upload_time, status, error_code, error_message, yonyou_file_id, retry_count,
                 local_file_path, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                business_id,
                doc_number,
                doc_type,
                product_type,
                new_filename,
                file_size,
                file_extension,
                upload_time_str,
                'pending',  # 初始状态
                None,
                None,
                None,
                0,
                local_file_path,
                upload_time_str,
                upload_time_str
            ))

            record_id = cursor.lastrowid
            conn.commit()

        # 添加后台任务
        background_tasks.add_task(
            background_upload_to_yonyou,
            file_content=file_content,
            new_filename=new_filename,
            business_id=business_id,
            business_type=business_type,
            local_file_path=local_file_path,
            record_id=record_id
        )

        records.append({
            "id": record_id,
            "file_name": new_filename,
            "original_name": upload_file.filename,
            "status": "pending",
            "file_size": file_size
        })

    # 立即返回响应
    return {
        "success": True,
        "total": len(files),
        "message": f"已接收{len(files)}个文件，正在后台上传中",
        "records": records
    }


def save_upload_history(history: UploadHistory):
    """保存上传历史到数据库（使用并发安全的数据库连接）"""
    from app.core.timezone import get_beijing_now_naive

    with get_db_connection() as conn:
        cursor = conn.cursor()

        # 获取北京时间
        beijing_now = get_beijing_now_naive()
        upload_time_str = beijing_now.isoformat()

        cursor.execute("""
            INSERT INTO upload_history
            (business_id, doc_number, doc_type, product_type, file_name, file_size, file_extension,
             upload_time, status, error_code, error_message, yonyou_file_id, retry_count,
             local_file_path, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            history.business_id,
            history.doc_number,
            history.doc_type,
            history.product_type,
            history.file_name,
            history.file_size,
            history.file_extension,
            upload_time_str,
            history.status,
            history.error_code,
            history.error_message,
            history.yonyou_file_id,
            history.retry_count,
            history.local_file_path,
            upload_time_str,
            upload_time_str
        ))

        conn.commit()
