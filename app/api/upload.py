from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from typing import List
import asyncio
import os
from datetime import datetime
from pathlib import Path
from app.core.config import get_settings
from app.core.yonyou_client import YonYouClient
from app.core.database import get_db_connection
from app.models.upload_history import UploadHistory

router = APIRouter()
settings = get_settings()
yonyou_client = YonYouClient()


def generate_unique_filename(doc_number: str, file_extension: str, storage_path: str) -> tuple[str, str]:
    """
    生成唯一的文件名

    Args:
        doc_number: 单据编号
        file_extension: 文件扩展名（如.jpg）
        storage_path: 存储路径

    Returns:
        tuple: (新文件名, 完整路径)
    """
    base_name = doc_number
    counter = 1
    new_filename = f"{base_name}{file_extension}"
    full_path = os.path.join(storage_path, new_filename)

    # 如果文件名已存在，添加流水号
    while os.path.exists(full_path):
        new_filename = f"{base_name}-{counter}{file_extension}"
        full_path = os.path.join(storage_path, new_filename)
        counter += 1

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


@router.post("/upload")
async def upload_files(
    business_id: str = Form(..., description="业务单据ID"),
    doc_number: str = Form(..., description="单据编号"),
    doc_type: str = Form(..., description="单据类型"),
    files: List[UploadFile] = File(...)
):
    """
    批量上传文件到用友云

    请求参数:
    - business_id: 业务单据ID（纯数字，用于用友云API）
    - doc_number: 单据编号（业务标识，如SO20250103001）
    - doc_type: 单据类型（销售/转库/其他）
    - files: 文件列表 (最多10个)

    响应格式:
    {
        "success": true,
        "total": 10,
        "succeeded": 9,
        "failed": 1,
        "results": [...]
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

    # 验证doc_number格式
    if not doc_number or len(doc_number.strip()) == 0:
        raise HTTPException(status_code=400, detail="doc_number不能为空")

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

    # 并发上传（限制并发数为3）
    semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_UPLOADS)

    async def upload_single_file(upload_file: UploadFile):
        async with semaphore:
            # 读取文件内容
            file_content = await upload_file.read()
            file_size = len(file_content)

            # 验证文件大小
            if file_size > settings.MAX_FILE_SIZE:
                return {
                    "file_name": upload_file.filename,
                    "success": False,
                    "error_code": "FILE_TOO_LARGE",
                    "error_message": f"文件大小超过{settings.MAX_FILE_SIZE / 1024 / 1024}MB限制"
                }

            # 获取文件扩展名
            file_extension = "." + upload_file.filename.split(".")[-1].lower()

            # 生成基于doc_number的唯一文件名
            storage_path = settings.LOCAL_STORAGE_PATH
            new_filename, local_file_path = generate_unique_filename(
                doc_number, file_extension, storage_path
            )

            # 创建上传历史记录
            history = UploadHistory(
                business_id=business_id,
                doc_number=doc_number,
                doc_type=doc_type,
                file_name=new_filename,  # 使用新文件名
                file_size=file_size,
                file_extension=file_extension,
                local_file_path=local_file_path,
                status="pending"
            )

            # 上传到用友云（使用新文件名）
            for attempt in range(settings.MAX_RETRY_COUNT):
                result = await yonyou_client.upload_file(
                    file_content,
                    new_filename,  # 上传到用友云时使用新文件名
                    business_id
                )

                if result["success"]:
                    # 更新历史记录
                    history.status = "success"
                    history.yonyou_file_id = result["data"]["id"]
                    history.retry_count = attempt

                    # 保存文件到本地
                    try:
                        save_file_locally(file_content, local_file_path)
                    except Exception as e:
                        # 本地保存失败不影响整体流程，仅记录日志
                        print(f"本地文件保存失败: {str(e)}")

                    # 保存到数据库
                    save_upload_history(history)

                    return {
                        "file_name": new_filename,
                        "original_name": upload_file.filename,
                        "success": True,
                        "file_id": result["data"]["id"],
                        "file_size": file_size,
                        "file_extension": result["data"].get("fileExtension", "")
                    }
                else:
                    if attempt < settings.MAX_RETRY_COUNT - 1:
                        await asyncio.sleep(settings.RETRY_DELAY)
                    else:
                        # 最后一次失败
                        history.status = "failed"
                        history.error_code = result["error_code"]
                        history.error_message = result["error_message"]
                        history.retry_count = attempt

                        # 保存到数据库
                        save_upload_history(history)

                        return {
                            "file_name": new_filename,
                            "original_name": upload_file.filename,
                            "success": False,
                            "error_code": result["error_code"],
                            "error_message": result["error_message"]
                        }

    # 并发执行上传
    results = await asyncio.gather(*[upload_single_file(f) for f in files])

    # 统计结果
    succeeded = sum(1 for r in results if r["success"])
    failed = len(results) - succeeded

    return {
        "success": True,
        "total": len(files),
        "succeeded": succeeded,
        "failed": failed,
        "results": results
    }


def save_upload_history(history: UploadHistory):
    """保存上传历史到数据库"""
    from app.core.timezone import get_beijing_now_naive

    conn = get_db_connection()
    cursor = conn.cursor()

    # 获取北京时间
    beijing_now = get_beijing_now_naive()
    upload_time_str = beijing_now.isoformat()

    cursor.execute("""
        INSERT INTO upload_history
        (business_id, doc_number, doc_type, file_name, file_size, file_extension,
         upload_time, status, error_code, error_message, yonyou_file_id, retry_count,
         local_file_path, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        history.business_id,
        history.doc_number,
        history.doc_type,
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
    conn.close()
