"""
物流链接管理API (管理侧)

为每个物流公司维护一条专属token链接, 管理员从这里查看/复制/重置链接,
并可手动触发发货单快照同步。
"""

import asyncio
import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from ..core import delivery_sync_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/")
async def list_logistics_links() -> Dict[str, Any]:
    """全部物流专属链接及各自待上传单据数"""
    try:
        state = delivery_sync_service.get_sync_state()
        links = delivery_sync_service.list_links_with_pending()
        return {
            "last_sync_at": state["last_sync_at"],
            "sync_status": state["last_status"],
            "links": links,
        }
    except Exception as e:
        logger.error(f"获取物流链接列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取物流链接列表失败: {str(e)}")


@router.post("/{link_id}/regenerate")
async def regenerate_link_token(link_id: int) -> Dict[str, Any]:
    """重置指定物流的token, 旧链接立即失效"""
    new_token = delivery_sync_service.regenerate_token(link_id)
    if new_token is None:
        raise HTTPException(status_code=404, detail="物流链接不存在")
    logger.info(f"物流链接token已重置: link_id={link_id}")
    return {
        "success": True,
        "token": new_token,
        "link_path": f"/l/{new_token}",
    }


@router.post("/sync", status_code=202)
async def trigger_manual_sync() -> Dict[str, Any]:
    """手动触发一轮快照同步(后台执行, 前端轮询 sync-status)"""
    if delivery_sync_service.is_sync_running():
        raise HTTPException(status_code=409, detail="同步正在进行中")

    remaining = delivery_sync_service.get_manual_cooldown_remaining()
    if remaining > 0:
        raise HTTPException(status_code=409, detail=f"操作过于频繁, 请{remaining}秒后再试")

    asyncio.create_task(delivery_sync_service.sync_delivery_snapshot(trigger="manual"))
    return {"started": True}


@router.get("/sync-status")
async def get_sync_status() -> Dict[str, Any]:
    """快照同步状态(手动触发后前端轮询)"""
    return delivery_sync_service.get_sync_state()
