"""
物流待上传门户API (物流侧, 对外)

物流公司通过专属token链接访问, 只能看到自己公司的待上传单据。
token即凭证, 无其他鉴权; 无效/禁用token统一返回404, 不泄露是否存在。
"""

import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from ..core import delivery_sync_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/{token}/deliveries")
async def get_pending_deliveries(token: str) -> Dict[str, Any]:
    """该物流公司的待上传单据清单(已排除本应用有上传记录的单据)"""
    data = delivery_sync_service.get_portal_data(token)
    if data is None:
        raise HTTPException(status_code=404, detail="链接无效或已失效")
    return data
