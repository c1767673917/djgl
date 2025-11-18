"""
定时任务调度器（修复版）
使用独立的任务函数避免序列化问题
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.executors.asyncio import AsyncIOExecutor

from .core.config import get_settings
from .core.file_manager import FileManager
from .core.backup_service import BackupService
from .core.database import get_db_connection
from .core.webdav_client import WebDAVClient

logger = logging.getLogger(__name__)

# 全局实例（在模块级别创建，避免序列化问题）
_file_manager = None
_backup_service = None
_settings = None


def get_file_manager():
    """获取文件管理器单例"""
    global _file_manager
    if _file_manager is None:
        _file_manager = FileManager()
    return _file_manager


def get_backup_service():
    """获取备份服务单例"""
    global _backup_service
    if _backup_service is None:
        _backup_service = BackupService()
    return _backup_service


def get_config():
    """获取配置单例"""
    global _settings
    if _settings is None:
        _settings = get_settings()
    return _settings


# ========== 独立的任务函数（避免序列化问题）==========

async def webdav_health_check_task():
    """WebDAV健康检查任务"""
    try:
        logger.debug("执行WebDAV健康检查任务")
        file_manager = get_file_manager()
        is_healthy = await file_manager.check_webdav_health()

        if is_healthy:
            logger.debug("WebDAV健康检查通过")
        else:
            logger.warning("WebDAV健康检查失败，服务不可用")

    except Exception as e:
        logger.error(f"WebDAV健康检查任务异常: {str(e)}")


async def cleanup_cache_task():
    """缓存清理任务"""
    try:
        logger.info("执行缓存清理任务")
        file_manager = get_file_manager()
        result = await file_manager.cleanup_cache()

        if 'error' in result:
            logger.error(f"缓存清理失败: {result['error']}")
        else:
            logger.info(
                f"缓存清理完成: 删除{result.get('deleted_files', 0)}个文件，"
                f"释放{result.get('freed_space', 0) / 1024 / 1024:.2f}MB空间"
            )

    except Exception as e:
        logger.error(f"缓存清理任务异常: {str(e)}")


async def database_backup_task():
    """数据库备份任务"""
    try:
        logger.info("执行数据库备份任务")
        settings = get_config()

        if not settings.BACKUP_ENABLED:
            logger.info("备份功能已禁用，跳过备份任务")
            return

        backup_service = get_backup_service()
        result = await backup_service.perform_backup()

        if result.get('success'):
            logger.info(
                f"备份任务完成: {result.get('backup_filename', 'unknown')} "
                f"({result.get('file_size', 0)} bytes), "
                f"上传{'成功' if result.get('uploaded') else '失败'}, "
                f"清理{result.get('cleaned_count', 0)}个过期文件"
            )
        else:
            logger.error(f"备份任务失败: {result.get('error', '未知错误')}")

    except Exception as e:
        logger.error(f"数据库备份任务异常: {str(e)}")


async def sync_pending_files_task():
    """待同步文件检查任务"""
    try:
        logger.debug("执行待同步文件检查任务")
        file_manager = get_file_manager()

        # 检查是否有待同步文件
        pending_count = await file_manager.get_pending_sync_count()
        if pending_count > 0:
            logger.info(f"发现{pending_count}个待同步文件，开始同步")
            result = await file_manager.sync_pending_files()

            if result.get('success'):
                logger.info(
                    f"同步完成: 成功{result.get('synced_count', 0)}个，"
                    f"失败{result.get('failed_count', 0)}个"
                )
            else:
                logger.warning(f"同步失败: {result.get('error', '未知错误')}")
        else:
            logger.debug("没有待同步文件")

    except Exception as e:
        logger.error(f"待同步文件检查任务异常: {str(e)}")


async def webdav_integrity_check_task(max_records: int = 200):
    """
    WebDAV文件完整性巡检任务

    设计目标:
        - 定期抽样检查upload_history中标记为success且存在webdav_path的记录,
          对比本地记录的file_size与WebDAV端实际文件大小,尽早发现远端0字节
          或大小不一致的问题,避免只有在管理员预览时才暴露。
        - 目前仅记录日志,不自动修改数据库状态,以免影响现有业务流程。
    """
    try:
        logger.info("执行WebDAV文件完整性检查任务")

        settings = get_config()
        file_manager = get_file_manager()

        # 先确认WebDAV可用
        if not await file_manager.check_webdav_health():
            logger.warning("WebDAV不可用,跳过完整性检查任务")
            return

        webdav_client = WebDAVClient()

        # 从数据库中抽取最近的记录进行检查,避免一次性全表扫描
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, file_name, file_size, webdav_path
                FROM upload_history
                WHERE status = 'success'
                  AND webdav_path IS NOT NULL
                  AND file_size IS NOT NULL
                  AND file_size > 0
                ORDER BY id DESC
                LIMIT ?
                """,
                (max_records,),
            )
            rows = cursor.fetchall()

        if not rows:
            logger.info("WebDAV完整性检查: 无需检查的记录")
            return

        problem_count = 0

        for row in rows:
            record_id = row["id"] if isinstance(row, dict) else row[0]
            file_name = row["file_name"] if isinstance(row, dict) else row[1]
            file_size = row["file_size"] if isinstance(row, dict) else row[2]
            webdav_path = row["webdav_path"] if isinstance(row, dict) else row[3]

            try:
                remote_size = await webdav_client.get_file_size(webdav_path)

                # 无法获取大小,记录警告但不中断整个任务
                if remote_size is None:
                    logger.warning(
                        f"[WebDAV完整性检查] 记录id={record_id}, 文件={file_name}, "
                        f"webdav_path={webdav_path} 无法获取远端大小"
                    )
                    continue

                # 远端为0字节或大小不一致,都记为潜在问题
                if remote_size == 0 or remote_size != file_size:
                    problem_count += 1
                    logger.error(
                        f"[WebDAV完整性问题] id={record_id}, 文件={file_name}, "
                        f"本地file_size={file_size}, 远端size={remote_size}, "
                        f"webdav_path={webdav_path}"
                    )
            except Exception as e:
                logger.error(
                    f"[WebDAV完整性检查异常] id={record_id}, 文件={file_name}, 错误={str(e)}"
                )

        logger.info(
            f"WebDAV文件完整性检查完成: 共检查{len(rows)}条记录, "
            f"发现{problem_count}条疑似异常"
        )

    except Exception as e:
        logger.error(f"WebDAV文件完整性检查任务异常: {str(e)}")


# ========== 调度器类 ==========

class TaskScheduler:
    """定时任务调度器"""

    def __init__(self):
        self.settings = get_config()

        # 创建调度器（使用内存存储）
        executors = {
            'default': AsyncIOExecutor()
        }
        job_defaults = {
            'coalesce': True,
            'max_instances': 1,
            'misfire_grace_time': 30
        }

        self.scheduler = AsyncIOScheduler(
            executors=executors,
            job_defaults=job_defaults,
            timezone='Asia/Shanghai'
        )

        self._setup_jobs()

    def _setup_jobs(self):
        """设置定时任务"""
        logger.info("开始设置定时任务")

        # 1. WebDAV健康检查（每60秒）
        self.scheduler.add_job(
            func=webdav_health_check_task,  # 使用模块级函数
            trigger=IntervalTrigger(seconds=self.settings.HEALTH_CHECK_INTERVAL),
            id='webdav_health_check',
            name='WebDAV健康检查',
            replace_existing=True
        )
        logger.info(f"已设置WebDAV健康检查任务，间隔{self.settings.HEALTH_CHECK_INTERVAL}秒")

        # 2. 缓存清理任务（每日凌晨2点）
        self.scheduler.add_job(
            func=cleanup_cache_task,  # 使用模块级函数
            trigger=CronTrigger(hour=2, minute=0),
            id='cache_cleanup',
            name='缓存清理',
            replace_existing=True
        )
        logger.info("已设置缓存清理任务，每日凌晨2点执行")

        # 3. 数据库备份任务（每日凌晨0点）
        self.scheduler.add_job(
            func=database_backup_task,  # 使用模块级函数
            trigger=CronTrigger(hour=0, minute=0),
            id='database_backup',
            name='数据库备份',
            replace_existing=True
        )
        logger.info("已设置数据库备份任务，每日凌晨0点执行")

        # 4. 待同步文件检查（每5分钟）
        self.scheduler.add_job(
            func=sync_pending_files_task,  # 使用模块级函数
            trigger=IntervalTrigger(seconds=self.settings.SYNC_RETRY_INTERVAL),
            id='sync_pending_files',
            name='待同步文件检查',
            replace_existing=True
        )
        logger.info(f"已设置待同步文件检查任务，间隔{self.settings.SYNC_RETRY_INTERVAL}秒")

        # 5. WebDAV文件完整性检查任务（每日凌晨3点, 抽样最近N条记录）
        self.scheduler.add_job(
            func=webdav_integrity_check_task,
            trigger=CronTrigger(hour=3, minute=0),
            id='webdav_integrity_check',
            name='WebDAV文件完整性检查',
            replace_existing=True
        )
        logger.info("已设置WebDAV文件完整性检查任务，每日凌晨3点执行")

    async def start(self):
        """启动调度器"""
        try:
            self.scheduler.start()
            logger.info("定时任务调度器已启动")

            # 打印任务信息
            jobs = self.scheduler.get_jobs()
            logger.info(f"已加载 {len(jobs)} 个定时任务:")
            for job in jobs:
                next_run = job.next_run_time.strftime('%Y-%m-%d %H:%M:%S') if job.next_run_time else '未设置'
                logger.info(f"  - {job.id}: {job.name} (下次运行: {next_run})")

        except Exception as e:
            logger.error(f"启动调度器失败: {str(e)}")
            raise

    async def shutdown(self):
        """关闭调度器"""
        try:
            self.scheduler.shutdown(wait=True)
            logger.info("定时任务调度器已关闭")
        except Exception as e:
            logger.error(f"关闭调度器失败: {str(e)}")

    def get_job_status(self) -> Dict[str, Any]:
        """获取任务状态"""
        try:
            jobs = []
            for job in self.scheduler.get_jobs():
                jobs.append({
                    'id': job.id,
                    'name': job.name,
                    'next_run_time': job.next_run_time.isoformat() if job.next_run_time else None,
                    'trigger': str(job.trigger)
                })

            return {
                'scheduler_running': self.scheduler.running,
                'jobs': jobs,
                'total_jobs': len(jobs)
            }

        except Exception as e:
            logger.error(f"获取任务状态失败: {str(e)}")
            return {
                'scheduler_running': False,
                'jobs': [],
                'error': str(e)
            }

    async def trigger_job_manually(self, job_id: str) -> Dict[str, Any]:
        """手动触发任务"""
        try:
            logger.info(f"手动触发任务: {job_id}")

            if job_id == 'cache_cleanup':
                await cleanup_cache_task()
                return {'success': True, 'message': '缓存清理任务已执行'}
            elif job_id == 'database_backup':
                await database_backup_task()
                return {'success': True, 'message': '数据库备份任务已执行'}
            elif job_id == 'webdav_health_check':
                await webdav_health_check_task()
                return {'success': True, 'message': 'WebDAV健康检查任务已执行'}
            elif job_id == 'sync_pending_files':
                await sync_pending_files_task()
                return {'success': True, 'message': '待同步文件检查任务已执行'}
            elif job_id == 'webdav_integrity_check':
                await webdav_integrity_check_task()
                return {'success': True, 'message': 'WebDAV文件完整性检查任务已执行'}
            else:
                return {'success': False, 'error': f'未知任务ID: {job_id}'}

        except Exception as e:
            error_msg = f"手动触发任务失败: {str(e)}"
            logger.error(error_msg)
            return {'success': False, 'error': error_msg}


# 全局调度器实例
scheduler_instance = None


async def start_scheduler():
    """启动全局调度器"""
    global scheduler_instance
    if scheduler_instance is None:
        scheduler_instance = TaskScheduler()
        await scheduler_instance.start()


async def stop_scheduler():
    """停止全局调度器"""
    global scheduler_instance
    if scheduler_instance:
        await scheduler_instance.shutdown()
        scheduler_instance = None


def get_scheduler() -> TaskScheduler:
    """获取调度器实例"""
    global scheduler_instance
    if scheduler_instance is None:
        raise Exception("调度器尚未启动")
    return scheduler_instance
