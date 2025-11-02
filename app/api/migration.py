"""
文件迁移API
迁移接口实现
进度查询、错误处理
批量操作支持
"""

import asyncio
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
import logging

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

from ..core.config import get_settings
from ..core.webdav_client import WebDAVClient
from ..core.database import get_db_connection
from ..core.timezone import get_beijing_now_naive, get_beijing_now_naive_iso

logger = logging.getLogger(__name__)

router = APIRouter()
settings = get_settings()
webdav_client = WebDAVClient()

# 全局迁移任务状态
migration_tasks: Dict[str, Dict] = {}


class MigrationRequest(BaseModel):
    """迁移请求模型"""
    dry_run: bool = False  # 是否为演练模式


class MigrationProgress(BaseModel):
    """迁移进度信息"""
    total: int
    completed: int
    failed: int
    percentage: float


class MigrationStatus(BaseModel):
    """迁移状态响应模型"""
    success: bool
    migration_id: str
    status: str
    progress: Optional[MigrationProgress] = None
    errors: Optional[List[Dict[str, str]]] = None
    message: Optional[str] = None


def _generate_migration_id() -> str:
    """生成迁移任务ID"""
    return str(uuid.uuid4())


def _get_migration_status(migration_id: str) -> Optional[Dict]:
    """获取迁移任务状态"""
    return migration_tasks.get(migration_id)


def _update_migration_status(migration_id: str, updates: Dict):
    """更新迁移任务状态"""
    if migration_id in migration_tasks:
        migration_tasks[migration_id].update(updates)


async def _get_local_files_to_migrate() -> List[Dict[str, Any]]:
    """获取需要迁移的本地文件列表"""
    try:
        files = []
        with get_db_connection() as conn:
            cursor = conn.cursor()

            # 查询已成功上传但未同步到WebDAV的文件
            cursor.execute("""
                SELECT id, file_name, local_file_path, upload_time, file_size
                FROM upload_history
                WHERE status = 'success'
                AND local_file_path IS NOT NULL
                AND (webdav_path IS NULL OR webdav_path = '')
                ORDER BY upload_time ASC
            """)

            for row in cursor.fetchall():
                file_path = row[2]
                if os.path.exists(file_path):
                    files.append({
                        'id': row[0],
                        'filename': row[1],
                        'local_path': file_path,
                        'upload_time': row[3],
                        'file_size': row[4]
                    })

        return files

    except Exception as e:
        logger.error(f"获取本地文件列表失败: {str(e)}")
        return []


def _generate_webdav_path(filename: str, upload_time: str) -> str:
    """生成WebDAV路径"""
    try:
        dt = datetime.fromisoformat(upload_time.replace('Z', '+00:00'))
        date_path = dt.strftime('%Y/%m/%d')
        return f"files/{date_path}/{filename}"
    except:
        # 如果时间解析失败，使用当前时间
        now = get_beijing_now_naive()
        date_path = now.strftime('%Y/%m/%d')
        return f"files/{date_path}/{filename}"


async def background_migration_task(
    migration_id: str,
    dry_run: bool = False,
    progress_callback: Optional[callable] = None
):
    """后台迁移任务"""
    try:
        # 更新状态为运行中
        _update_migration_status(migration_id, {
            'status': 'running',
            'start_time': get_beijing_now_naive_iso()
        })

        logger.info(f"开始执行迁移任务: {migration_id} (演练模式: {dry_run})")

        # 获取需要迁移的文件列表
        files = await _get_local_files_to_migrate()
        total_files = len(files)

        if total_files == 0:
            _update_migration_status(migration_id, {
                'status': 'completed',
                'message': '没有需要迁移的文件'
            })
            return

        # 更新进度信息
        _update_migration_status(migration_id, {
            'progress': {
                'total': total_files,
                'completed': 0,
                'failed': 0,
                'percentage': 0.0
            }
        })

        completed_count = 0
        failed_count = 0
        errors = []

        # 逐个迁移文件
        for i, file_info in enumerate(files):
            try:
                file_id = file_info['id']
                filename = file_info['filename']
                local_path = file_info['local_path']
                upload_time = file_info['upload_time']

                # 生成WebDAV路径
                webdav_path = _generate_webdav_path(filename, upload_time)

                if not dry_run:
                    # 实际迁移：上传到WebDAV
                    upload_result = await webdav_client.upload_file(local_path, webdav_path)

                    if upload_result['success']:
                        # 更新数据库记录
                        with get_db_connection() as conn:
                            cursor = conn.cursor()
                            cursor.execute("""
                                UPDATE upload_history
                                SET webdav_path = ?, is_cached = 1, updated_at = ?
                                WHERE id = ?
                            """, (webdav_path, get_beijing_now_naive_iso(), file_id))
                            conn.commit()

                        # 删除本地文件（可选，这里保留本地文件作为备份）
                        # os.remove(local_path)

                        completed_count += 1
                        logger.info(f"文件迁移成功: {filename} -> {webdav_path}")
                    else:
                        failed_count += 1
                        error_msg = upload_result.get('error', '上传失败')
                        errors.append({
                            'filename': filename,
                            'error': error_msg
                        })
                        logger.error(f"文件迁移失败: {filename} - {error_msg}")
                else:
                    # 演练模式：只模拟，不实际操作
                    completed_count += 1
                    logger.info(f"[演练] 文件迁移: {filename} -> {webdav_path}")

                # 更新进度
                percentage = ((i + 1) / total_files) * 100
                _update_migration_status(migration_id, {
                    'progress': {
                        'total': total_files,
                        'completed': completed_count,
                        'failed': failed_count,
                        'percentage': round(percentage, 1)
                    }
                })

                # 调用进度回调
                if progress_callback:
                    await progress_callback(migration_id, {
                        'total': total_files,
                        'completed': completed_count + failed_count,
                        'percentage': percentage
                    })

                # 添加小延迟，避免过快操作
                await asyncio.sleep(0.1)

            except Exception as e:
                failed_count += 1
                error_msg = str(e)
                errors.append({
                    'filename': file_info['filename'],
                    'error': error_msg
                })
                logger.error(f"迁移文件异常: {file_info['filename']} - {error_msg}")

        # 完成迁移
        final_status = 'completed' if failed_count == 0 else 'completed_with_errors'
        final_message = f"迁移完成: 成功{completed_count}个，失败{failed_count}个"

        _update_migration_status(migration_id, {
            'status': final_status,
            'end_time': get_beijing_now_naive_iso(),
            'message': final_message,
            'errors': errors
        })

        logger.info(f"迁移任务完成: {migration_id} - {final_message}")

    except Exception as e:
        error_msg = f"迁移任务异常: {str(e)}"
        logger.error(error_msg)

        _update_migration_status(migration_id, {
            'status': 'failed',
            'end_time': get_beijing_now_naive_iso(),
            'error': error_msg
        })


@router.post("/start", response_model=Dict[str, Any])
async def start_migration(
    request: MigrationRequest,
    background_tasks: BackgroundTasks
):
    """
    开始文件迁移

    - **dry_run**: 演练模式，不实际执行迁移操作
    """
    try:
        # 检查是否已有运行中的迁移任务
        running_tasks = [
            task_id for task_id, task in migration_tasks.items()
            if task.get('status') in ['running', 'pending']
        ]

        if running_tasks:
            raise HTTPException(
                status_code=409,
                detail=f"已有运行中的迁移任务: {running_tasks[0]}"
            )

        # 生成迁移任务ID
        migration_id = _generate_migration_id()

        # 创建迁移任务状态
        files = await _get_local_files_to_migrate()
        migration_tasks[migration_id] = {
            'migration_id': migration_id,
            'status': 'pending',
            'total_files': len(files),
            'progress': {
                'total': len(files),
                'completed': 0,
                'failed': 0,
                'percentage': 0.0
            },
            'created_at': get_beijing_now_naive_iso(),
            'dry_run': request.dry_run
        }

        # 添加后台任务
        background_tasks.add_task(
            background_migration_task,
            migration_id=migration_id,
            dry_run=request.dry_run
        )

        logger.info(f"迁移任务已启动: {migration_id}")

        return {
            "success": True,
            "migration_id": migration_id,
            "total_files": len(files),
            "dry_run": request.dry_run,
            "message": f"迁移任务已启动 ({'演练模式' if request.dry_run else '正式模式'})"
        }

    except Exception as e:
        error_msg = f"启动迁移任务失败: {str(e)}"
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)


@router.get("/status/{migration_id}", response_model=MigrationStatus)
async def get_migration_status(migration_id: str):
    """查询迁移状态"""
    try:
        task = _get_migration_status(migration_id)

        if not task:
            raise HTTPException(status_code=404, detail="迁移任务不存在")

        return MigrationStatus(
            success=True,
            migration_id=migration_id,
            status=task.get('status', 'unknown'),
            progress=task.get('progress'),
            errors=task.get('errors', []),
            message=task.get('message')
        )

    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"查询迁移状态失败: {str(e)}"
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)


@router.get("/list")
async def list_migration_tasks():
    """列出所有迁移任务"""
    try:
        tasks = []
        for migration_id, task in migration_tasks.items():
            tasks.append({
                'migration_id': migration_id,
                'status': task.get('status'),
                'total_files': task.get('total_files', 0),
                'created_at': task.get('created_at'),
                'start_time': task.get('start_time'),
                'end_time': task.get('end_time'),
                'dry_run': task.get('dry_run', False),
                'progress': task.get('progress', {})
            })

        # 按创建时间倒序排列
        tasks.sort(key=lambda x: x.get('created_at', ''), reverse=True)

        return {
            "success": True,
            "tasks": tasks,
            "total": len(tasks)
        }

    except Exception as e:
        error_msg = f"列出迁移任务失败: {str(e)}"
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)


@router.delete("/cleanup")
async def cleanup_migration_history():
    """清理迁移历史（保留最近10个）"""
    try:
        # 按创建时间排序，保留最新的10个
        sorted_tasks = sorted(
            migration_tasks.items(),
            key=lambda x: x[1].get('created_at', ''),
            reverse=True
        )

        to_delete = sorted_tasks[10:]  # 删除第10个之后的任务
        deleted_count = 0

        for migration_id, task in to_delete:
            # 只删除已完成的任务
            if task.get('status') in ['completed', 'completed_with_errors', 'failed']:
                del migration_tasks[migration_id]
                deleted_count += 1

        return {
            "success": True,
            "deleted_count": deleted_count,
            "remaining_count": len(migration_tasks),
            "message": f"已清理{deleted_count}个历史迁移任务"
        }

    except Exception as e:
        error_msg = f"清理迁移历史失败: {str(e)}"
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)


@router.get("/stats")
async def get_migration_stats():
    """获取迁移统计信息"""
    try:
        # 获取本地文件统计
        local_files = await _get_local_files_to_migrate()
        local_count = len(local_files)
        local_size = sum(f['file_size'] for f in local_files)

        # 获取已迁移文件统计
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*), SUM(file_size)
                FROM upload_history
                WHERE status = 'success' AND webdav_path IS NOT NULL AND webdav_path != ''
            """)
            migrated_stats = cursor.fetchone() or (0, 0)

        migrated_count = migrated_stats[0] or 0
        migrated_size = migrated_stats[1] or 0

        return {
            "success": True,
            "local_files": {
                "count": local_count,
                "size": local_size,
                "size_mb": round(local_size / 1024 / 1024, 2)
            },
            "migrated_files": {
                "count": migrated_count,
                "size": migrated_size,
                "size_mb": round(migrated_size / 1024 / 1024, 2)
            },
            "total_files": local_count + migrated_count,
            "migration_progress": round(
                (migrated_count / (local_count + migrated_count) * 100) if (local_count + migrated_count) > 0 else 0,
                2
            )
        }

    except Exception as e:
        error_msg = f"获取迁移统计失败: {str(e)}"
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)
