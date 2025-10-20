from datetime import datetime
from typing import Optional
from app.core.timezone import get_beijing_now_naive


class UploadHistory:
    def __init__(
        self,
        id: Optional[int] = None,
        business_id: str = "",
        doc_number: Optional[str] = None,
        doc_type: Optional[str] = None,
        product_type: Optional[str] = None,
        file_name: str = "",
        file_size: int = 0,
        file_extension: str = "",
        upload_time: Optional[datetime] = None,
        status: str = "pending",
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
        yonyou_file_id: Optional[str] = None,
        retry_count: int = 0,
        local_file_path: Optional[str] = None
    ):
        self.id = id
        self.business_id = business_id
        self.doc_number = doc_number
        self.doc_type = doc_type
        self.product_type = product_type
        self.file_name = file_name
        self.file_size = file_size
        self.file_extension = file_extension
        self.upload_time = upload_time or get_beijing_now_naive()
        self.status = status
        self.error_code = error_code
        self.error_message = error_message
        self.yonyou_file_id = yonyou_file_id
        self.retry_count = retry_count
        self.local_file_path = local_file_path
