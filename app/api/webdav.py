"""
WebDAV状态API
WebDAV状态查询
健康检查、同步状态
管理接口
"""

from typing import Dict, List, Optional, Any
import logging
import os
import tempfile

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

from ..core.config import get_settings
from ..core.webdav_client import WebDAVClient
from ..core.file_manager import FileManager
from ..core.backup_service import BackupService
from ..core.timezone import get_beijing_now_naive_iso

logger = logging.getLogger(__name__)

router = APIRouter()
settings = get_settings()
webdav_client = WebDAVClient()
file_manager = FileManager()
backup_service = BackupService()


class SyncRequest(BaseModel):
    """同步请求模型"""
    force: bool = False  # 是否强制同步


class WebDAVStatusResponse(BaseModel):
    """WebDAV状态响应模型"""
    success: bool
    webdav_available: bool
    last_check: Optional[str] = None
    pending_sync_count: int = 0
    total_cached_files: int = 0
    cache_size_mb: float = 0.0
    message: Optional[str] = None


class BackupStatusResponse(BaseModel):
    """备份状态响应模型"""
    success: bool
    last_backup: Optional[Dict[str, Any]] = None
    next_backup: Optional[str] = None
    backup_count: int = 0
    total_size_mb: float = 0.0
    webdav_backup_count: int = 0


@router.get("/status", response_model=WebDAVStatusResponse)
async def get_webdav_status():
    """获取WebDAV服务状态"""
    try:
        # 检查WebDAV可用性
        webdav_available = await file_manager.check_webdav_health()

        # 获取缓存统计
        cache_stats = await file_manager.get_cache_stats()

        # 获取待同步文件数量
        pending_sync_count = await file_manager.get_pending_sync_count()

        return WebDAVStatusResponse(
            success=True,
            webdav_available=webdav_available,
            last_check=get_beijing_now_naive_iso(),
            pending_sync_count=pending_sync_count,
            total_cached_files=cache_stats.get('total_files', 0),
            cache_size_mb=cache_stats.get('total_size_mb', 0.0),
            message="WebDAV服务正常" if webdav_available else "WebDAV服务不可用"
        )

    except Exception as e:
        error_msg = f"获取WebDAV状态失败: {str(e)}"
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)


@router.post("/sync")
async def trigger_sync(request: SyncRequest, background_tasks: BackgroundTasks):
    """手动触发同步"""
    try:
        # 检查WebDAV可用性
        webdav_available = await file_manager.check_webdav_health()
        if not webdav_available:
            raise HTTPException(
                status_code=503,
                detail="WebDAV服务不可用，无法执行同步"
            )

        # 获取待同步文件数量
        pending_count = await file_manager.get_pending_sync_count()
        if pending_count == 0 and not request.force:
            return {
                "success": True,
                "sync_started": False,
                "pending_files": 0,
                "message": "没有待同步文件"
            }

        # 添加后台同步任务
        background_tasks.add_task(file_manager.sync_pending_files)

        logger.info(f"手动触发同步任务，待同步文件数: {pending_count}")

        return {
            "success": True,
            "sync_started": True,
            "pending_files": pending_count,
            "message": f"同步任务已启动，{pending_count}个文件待同步"
        }

    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"触发同步失败: {str(e)}"
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)


@router.get("/files")
async def list_webdav_files(path: str = "/"):
    """列出WebDAV文件"""
    try:
        # 检查WebDAV可用性
        webdav_available = await file_manager.check_webdav_health()
        if not webdav_available:
            raise HTTPException(
                status_code=503,
                detail="WebDAV服务不可用"
            )

        # 获取文件列表
        files = await webdav_client.list_files(path)

        return {
            "success": True,
            "path": path,
            "files": files,
            "total_count": len(files)
        }

    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"列出WebDAV文件失败: {str(e)}"
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)


@router.get("/health")
async def detailed_health_check():
    """详细健康检查"""
    try:
        health_info = {
            "webdav_connection": False,
            "webdav_auth": False,
            "webdav_write": False,
            "webdav_read": False,
            "cache_directory": False,
            "temp_directory": False,
            "overall_status": "unhealthy"
        }

        # 检查WebDAV连接
        try:
            # 基本连接测试
            health_info["webdav_connection"] = await webdav_client.health_check()

            # 认证测试（尝试列出根目录）
            if health_info["webdav_connection"]:
                await webdav_client.list_files("/")
                health_info["webdav_auth"] = True

                # 写入测试（创建测试文件）
                test_content = b"health_check_test"
                test_path = "/health_check_test.txt"

                # 创建临时文件用于上传测试
                with tempfile.NamedTemporaryFile(mode='wb', delete=False) as temp_file:
                    temp_file.write(test_content)
                    temp_file_path = temp_file.name

                try:
                    upload_result = await webdav_client.upload_file(
                        temp_file_path, test_path
                    )
                    if upload_result.get('success'):
                        health_info["webdav_write"] = True

                        # 读取测试
                        try:
                            downloaded_content = await webdav_client.download_file(test_path)
                            # 验证下载内容与上传内容一致
                            if downloaded_content == test_content:
                                health_info["webdav_read"] = True

                            # 清理测试文件
                            await webdav_client.delete_file(test_path)
                        except:
                            pass
                finally:
                    # 清理临时文件
                    if os.path.exists(temp_file_path):
                        os.remove(temp_file_path)

        except Exception as e:
            logger.warning(f"WebDAV健康检查异常: {str(e)}")

        # 检查目录
        health_info["cache_directory"] = os.path.exists(settings.CACHE_DIR)
        health_info["temp_directory"] = os.path.exists(settings.TEMP_STORAGE_DIR)

        # 判断整体状态
        # 只统计布尔值检查项,排除字符串类型的overall_status
        healthy_checks = sum(1 for v in health_info.values() if isinstance(v, bool) and v)
        total_checks = sum(1 for v in health_info.values() if isinstance(v, bool))

        if healthy_checks == total_checks:
            health_info["overall_status"] = "healthy"
        elif healthy_checks >= total_checks * 0.7:
            health_info["overall_status"] = "degraded"
        else:
            health_info["overall_status"] = "unhealthy"

        health_info["check_time"] = get_beijing_now_naive_iso()
        health_info["healthy_checks"] = healthy_checks
        health_info["total_checks"] = total_checks

        return {
            "success": True,
            "health": health_info
        }

    except Exception as e:
        error_msg = f"详细健康检查失败: {str(e)}"
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)


@router.get("/cache/stats")
async def get_cache_statistics():
    """获取缓存统计信息"""
    try:
        cache_stats = await file_manager.get_cache_stats()

        # 获取缓存使用率
        cache_dir = cache_stats.get('cache_dir', settings.CACHE_DIR)
        try:
            stat = os.statvfs(cache_dir)
            total_space = stat.f_frsize * stat.f_blocks
            free_space = stat.f_frsize * stat.f_bavail
            used_space = total_space - free_space
            cache_usage = cache_stats.get('total_size', 0)

            cache_stats.update({
                'disk_total_space': total_space,
                'disk_free_space': free_space,
                'disk_used_space': used_space,
                'cache_usage_percent': round((cache_usage / total_space) * 100, 2) if total_space > 0 else 0
            })
        except:
            cache_stats.update({
                'disk_total_space': 0,
                'disk_free_space': 0,
                'disk_used_space': 0,
                'cache_usage_percent': 0
            })

        return {
            "success": True,
            "cache_stats": cache_stats
        }

    except Exception as e:
        error_msg = f"获取缓存统计失败: {str(e)}"
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)


@router.post("/cache/cleanup")
async def trigger_cache_cleanup(background_tasks: BackgroundTasks):
    """触发缓存清理"""
    try:
        # 添加后台清理任务
        background_tasks.add_task(file_manager.cleanup_cache)

        logger.info("手动触发缓存清理任务")

        return {
            "success": True,
            "message": "缓存清理任务已启动"
        }

    except Exception as e:
        error_msg = f"触发缓存清理失败: {str(e)}"
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)


@router.get("/backup/status", response_model=BackupStatusResponse)
async def get_backup_status():
    """获取备份状态"""
    try:
        backup_status = await backup_service.get_backup_status()

        return BackupStatusResponse(
            success=True,
            last_backup=backup_status.get('last_backup'),
            next_backup=backup_status.get('next_backup'),
            backup_count=backup_status.get('backup_count', 0),
            total_size_mb=backup_status.get('total_size_mb', 0.0),
            webdav_backup_count=backup_status.get('webdav_backup_count', 0)
        )

    except Exception as e:
        error_msg = f"获取备份状态失败: {str(e)}"
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)


@router.post("/backup/trigger")
async def trigger_backup(background_tasks: BackgroundTasks):
    """手动触发备份"""
    try:
        # 检查备份功能是否启用
        if not settings.BACKUP_ENABLED:
            raise HTTPException(
                status_code=403,
                detail="备份功能已禁用"
            )

        # 添加后台备份任务
        background_tasks.add_task(backup_service.manual_backup)

        logger.info("手动触发备份任务")

        return {
            "success": True,
            "backup_started": True,
            "message": "备份任务已启动"
        }

    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"触发备份失败: {str(e)}"
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)


@router.get("/config")
async def get_webdav_config():
    """获取WebDAV配置信息（隐藏敏感信息）"""
    try:
        config = {
            "webdav_url": settings.WEBDAV_URL,
            "username": settings.WEBDAV_USERNAME,
            "base_path": settings.WEBDAV_BASE_PATH,
            "timeout": settings.WEBDAV_TIMEOUT,
            "retry_count": settings.WEBDAV_RETRY_COUNT,
            "retry_delay": settings.WEBDAV_RETRY_DELAY,
            "cache_dir": settings.CACHE_DIR,
            "cache_days": settings.CACHE_DAYS,
            "temp_storage_dir": settings.TEMP_STORAGE_DIR,
            "backup_enabled": settings.BACKUP_ENABLED,
            "backup_retention_days": settings.BACKUP_RETENTION_DAYS,
            "health_check_interval": settings.HEALTH_CHECK_INTERVAL,
            "sync_retry_interval": settings.SYNC_RETRY_INTERVAL
        }

        return {
            "success": True,
            "config": config
        }

    except Exception as e:
        error_msg = f"获取WebDAV配置失败: {str(e)}"
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)


@router.post("/test-connection")
async def test_webdav_connection():
    """测试WebDAV连接"""
    try:
        result = await webdav_client.health_check()

        if result:
            # 进一步测试读写权限
            test_results = {
                "connection": True,
                "authentication": False,
                "write_permission": False,
                "read_permission": False
            }

            try:
                # 测试认证
                await webdav_client.list_files("/")
                test_results["authentication"] = True

                # 测试写入权限
                test_file = "/connection_test.txt"
                test_content = b"test"

                # 创建临时文件用于上传测试
                with tempfile.NamedTemporaryFile(mode='wb', delete=False) as temp_file:
                    temp_file.write(test_content)
                    temp_file_path = temp_file.name

                try:
                    upload_result = await webdav_client.upload_file(temp_file_path, test_file)
                    if upload_result.get('success'):
                        test_results["write_permission"] = True

                        # 测试读取权限
                        downloaded_content = await webdav_client.download_file(test_file)
                        if downloaded_content == test_content:
                            test_results["read_permission"] = True

                        # 清理测试文件
                        await webdav_client.delete_file(test_file)
                finally:
                    # 清理临时文件
                    if os.path.exists(temp_file_path):
                        os.remove(temp_file_path)

            except Exception as e:
                logger.warning(f"WebDAV权限测试异常: {str(e)}")

            return {
                "success": True,
                "test_results": test_results,
                "message": "WebDAV连接测试完成"
            }
        else:
            return {
                "success": False,
                "test_results": {
                    "connection": False,
                    "authentication": False,
                    "write_permission": False,
                    "read_permission": False
                },
                "message": "WebDAV连接失败"
            }

    except Exception as e:
        error_msg = f"测试WebDAV连接失败: {str(e)}"
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)
