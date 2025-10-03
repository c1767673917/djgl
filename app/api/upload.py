from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from typing import List
import asyncio
from datetime import datetime
from app.core.config import get_settings
from app.core.yonyou_client import YonYouClient
from app.core.database import get_db_connection
from app.models.upload_history import UploadHistory

router = APIRouter()
settings = get_settings()
yonyou_client = YonYouClient()


@router.post("/upload")
async def upload_files(
    business_id: str = Form(...),
    files: List[UploadFile] = File(...)
):
    """
    批量上传文件到用友云

    请求参数:
    - business_id: 业务单据ID
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

            # 创建上传历史记录
            history = UploadHistory(
                business_id=business_id,
                file_name=upload_file.filename,
                file_size=file_size,
                file_extension="." + upload_file.filename.split(".")[-1].lower(),
                status="pending"
            )

            # 上传到用友云（带重试）
            for attempt in range(settings.MAX_RETRY_COUNT):
                result = await yonyou_client.upload_file(
                    file_content,
                    upload_file.filename,
                    business_id
                )

                if result["success"]:
                    # 更新历史记录
                    history.status = "success"
                    history.yonyou_file_id = result["data"]["id"]
                    history.retry_count = attempt

                    # 保存到数据库
                    save_upload_history(history)

                    return {
                        "file_name": upload_file.filename,
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
                            "file_name": upload_file.filename,
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
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO upload_history
        (business_id, file_name, file_size, file_extension, status,
         error_code, error_message, yonyou_file_id, retry_count)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        history.business_id,
        history.file_name,
        history.file_size,
        history.file_extension,
        history.status,
        history.error_code,
        history.error_message,
        history.yonyou_file_id,
        history.retry_count
    ))

    conn.commit()
    conn.close()
