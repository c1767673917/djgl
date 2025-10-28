"""
备份服务
数据库备份实现
WebDAV上传、压缩、清理逻辑
备份状态管理
"""

import os
import tarfile
import tempfile
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
import logging

from .config import get_settings
from .webdav_client import WebDAVClient
from .database import get_db_connection

logger = logging.getLogger(__name__)


class BackupService:
    """备份服务"""

    def __init__(self):
        self.settings = get_settings()
        self.webdav_client = WebDAVClient()

        # 备份相关路径
        self.db_path = "data/uploads.db"
        self.env_path = ".env"
        self.backup_dir = "temp_backups"

        # 确保备份目录存在
        os.makedirs(self.backup_dir, exist_ok=True)

        logger.info("备份服务初始化完成")
        logger.info(f"数据库路径: {self.db_path}")
        logger.info(f"配置文件路径: {self.env_path}")
        logger.info(f"备份保留天数: {self.settings.BACKUP_RETENTION_DAYS}")

    def _generate_backup_filename(self) -> str:
        """生成备份文件名"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"backup_{timestamp}.tar.gz"

    def _get_backup_webdav_path(self, filename: str) -> str:
        """获取WebDAV备份路径"""
        return f"backups/{filename}"

    async def create_backup(self) -> Dict[str, Any]:
        """创建数据库备份"""
        backup_filename = self._generate_backup_filename()
        backup_path = os.path.join(self.backup_dir, backup_filename)

        logger.info(f"开始创建备份: {backup_filename}")

        result = {
            'success': False,
            'filename': backup_filename,
            'backup_path': backup_path,
            'file_size': 0,
            'error': None,
            'created_at': datetime.now().isoformat()
        }

        try:
            # 检查数据库文件是否存在
            if not os.path.exists(self.db_path):
                raise Exception(f"数据库文件不存在: {self.db_path}")

            # 创建压缩包
            with tarfile.open(backup_path, 'w:gz', compresslevel=self.settings.BACKUP_COMPRESSION_LEVEL) as tar:
                # 添加数据库文件
                db_arcname = os.path.basename(self.db_path)
                tar.add(self.db_path, arcname=db_arcname)
                logger.debug(f"已添加数据库文件: {self.db_path}")

                # 添加配置文件（如果存在）
                if os.path.exists(self.env_path):
                    env_arcname = os.path.basename(self.env_path)
                    tar.add(self.env_path, arcname=env_arcname)
                    logger.debug(f"已添加配置文件: {self.env_path}")

                # 添加备份元数据
                metadata_content = self._generate_backup_metadata()
                metadata_path = os.path.join(self.backup_dir, "metadata.json")
                with open(metadata_path, 'w', encoding='utf-8') as f:
                    f.write(metadata_content)
                tar.add(metadata_path, arcname="backup_metadata.json")
                os.remove(metadata_path)  # 清理临时元数据文件

            # 检查备份文件大小
            file_size = os.path.getsize(backup_path)
            result['file_size'] = file_size

            if file_size < 1024:  # 小于1KB可能有问题
                raise Exception("备份文件大小异常，可能创建失败")

            logger.info(f"备份创建成功: {backup_filename} ({file_size} bytes)")
            result['success'] = True

        except Exception as e:
            error_msg = f"创建备份失败: {str(e)}"
            logger.error(error_msg)

            # 清理失败的备份文件
            if os.path.exists(backup_path):
                os.remove(backup_path)

            result['error'] = error_msg

        return result

    def _generate_backup_metadata(self) -> str:
        """生成备份元数据"""
        import json

        metadata = {
            'backup_time': datetime.now().isoformat(),
            'app_name': self.settings.APP_NAME,
            'app_version': self.settings.APP_VERSION,
            'database_path': self.db_path,
            'config_included': os.path.exists(self.env_path),
            'compression_level': self.settings.BACKUP_COMPRESSION_LEVEL,
            'backup_type': 'scheduled'
        }

        return json.dumps(metadata, ensure_ascii=False, indent=2)

    async def upload_backup(self, backup_path: str) -> bool:
        """上传备份到WebDAV"""
        try:
            filename = os.path.basename(backup_path)
            webdav_path = self._get_backup_webdav_path(filename)

            logger.info(f"开始上传备份到WebDAV: {webdav_path}")

            # 确保备份目录存在
            await self.webdav_client.create_directory("backups")

            # 上传备份文件
            upload_result = await self.webdav_client.upload_file(backup_path, webdav_path)

            if upload_result['success']:
                logger.info(f"备份上传成功: {webdav_path}")
                return True
            else:
                logger.error(f"备份上传失败: {upload_result.get('error')}")
                return False

        except Exception as e:
            error_msg = f"上传备份异常: {str(e)}"
            logger.error(error_msg)
            return False

    async def cleanup_old_backups(self) -> int:
        """清理过期备份"""
        try:
            logger.info("开始清理过期备份")

            deleted_count = 0
            cutoff_date = datetime.now() - timedelta(days=self.settings.BACKUP_RETENTION_DAYS)

            # 清理本地备份文件
            try:
                backup_dir = Path(self.backup_dir)
                if backup_dir.exists():
                    for backup_file in backup_dir.glob("backup_*.tar.gz"):
                        try:
                            # 从文件名解析时间
                            filename = backup_file.name
                            timestamp_str = filename.replace("backup_", "").replace(".tar.gz", "")
                            file_date = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")

                            if file_date < cutoff_date:
                                backup_file.unlink()
                                deleted_count += 1
                                logger.debug(f"删除本地过期备份: {filename}")
                        except Exception as e:
                            logger.warning(f"处理本地备份文件失败 {backup_file.name}: {str(e)}")
            except Exception as e:
                logger.error(f"清理本地备份失败: {str(e)}")

            # 清理WebDAV备份文件
            try:
                webdav_files = await self.webdav_client.list_files("backups")
                for file_info in webdav_files:
                    if not file_info['name'].startswith("backup_") or not file_info['name'].endswith(".tar.gz"):
                        continue

                    try:
                        # 从文件名解析时间
                        filename = file_info['name']
                        timestamp_str = filename.replace("backup_", "").replace(".tar.gz", "")
                        file_date = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")

                        if file_date < cutoff_date:
                            webdav_path = f"backups/{filename}"
                            success = await self.webdav_client.delete_file(webdav_path)
                            if success:
                                deleted_count += 1
                                logger.debug(f"删除WebDAV过期备份: {webdav_path}")
                            else:
                                logger.warning(f"删除WebDAV备份失败: {webdav_path}")
                    except Exception as e:
                        logger.warning(f"处理WebDAV备份文件失败 {file_info['name']}: {str(e)}")
            except Exception as e:
                logger.error(f"清理WebDAV备份失败: {str(e)}")

            logger.info(f"备份清理完成，删除了 {deleted_count} 个过期文件")
            return deleted_count

        except Exception as e:
            error_msg = f"清理过期备份失败: {str(e)}"
            logger.error(error_msg)
            return 0

    async def perform_backup(self) -> Dict[str, Any]:
        """执行完整备份流程"""
        logger.info("开始执行定时备份任务")

        result = {
            'success': False,
            'backup_filename': None,
            'file_size': 0,
            'uploaded': False,
            'cleaned_count': 0,
            'error': None,
            'started_at': datetime.now().isoformat()
        }

        try:
            # 1. 创建备份
            backup_result = await self.create_backup()
            if not backup_result['success']:
                result['error'] = backup_result['error']
                return result

            result['backup_filename'] = backup_result['filename']
            result['file_size'] = backup_result['file_size']

            # 2. 上传到WebDAV
            upload_success = await self.upload_backup(backup_result['backup_path'])
            result['uploaded'] = upload_success

            if not upload_success:
                logger.warning("备份上传失败，但本地备份已保存")

            # 3. 清理过期备份
            cleaned_count = await self.cleanup_old_backups()
            result['cleaned_count'] = cleaned_count

            # 4. 记录备份日志
            await self._log_backup_result(
                backup_result['filename'],
                backup_result['file_size'],
                'success' if upload_success else 'partial',
                None if upload_success else "WebDAV上传失败"
            )

            # 5. 清理本地临时文件
            if upload_success and os.path.exists(backup_result['backup_path']):
                os.remove(backup_result['backup_path'])
                logger.debug("已删除本地临时备份文件")

            result['success'] = True
            logger.info("定时备份任务执行成功")

        except Exception as e:
            error_msg = f"备份任务执行失败: {str(e)}"
            logger.error(error_msg)

            result['error'] = error_msg

            # 记录失败日志
            if result['backup_filename']:
                await self._log_backup_result(
                    result['backup_filename'],
                    result['file_size'],
                    'failed',
                    error_msg
                )

        result['completed_at'] = datetime.now().isoformat()
        return result

    async def _log_backup_result(self, filename: str, file_size: int, status: str, error_message: Optional[str]):
        """记录备份结果到数据库"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO backup_logs
                (backup_filename, backup_time, file_size, status, error_message, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                filename,
                datetime.now().isoformat(),
                file_size,
                status,
                error_message,
                datetime.now().isoformat()
            ))

            conn.commit()
            conn.close()

            logger.debug(f"备份日志已记录: {filename} - {status}")

        except Exception as e:
            logger.error(f"记录备份日志失败: {str(e)}")

    async def get_backup_status(self) -> Dict[str, Any]:
        """获取备份状态信息"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            # 获取最近的备份记录
            cursor.execute("""
                SELECT backup_filename, backup_time, file_size, status, error_message
                FROM backup_logs
                ORDER BY backup_time DESC
                LIMIT 1
            """)
            last_backup = cursor.fetchone()

            # 获取备份总数和总大小
            cursor.execute("""
                SELECT COUNT(*), SUM(file_size)
                FROM backup_logs
                WHERE backup_time >= datetime('now', '-30 days')
            """)
            backup_stats = cursor.fetchone()

            # 获取WebDAV备份文件列表
            webdav_backups = []
            try:
                webdav_files = await self.webdav_client.list_files("backups")
                webdav_backups = [f for f in webdav_files if f['name'].startswith("backup_")]
            except Exception as e:
                logger.warning(f"获取WebDAV备份列表失败: {str(e)}")

            conn.close()

            return {
                'last_backup': {
                    'filename': last_backup[0] if last_backup else None,
                    'time': last_backup[1] if last_backup else None,
                    'size': last_backup[2] if last_backup else 0,
                    'status': last_backup[3] if last_backup else None,
                    'error_message': last_backup[4] if last_backup else None
                } if last_backup else None,
                'backup_count': backup_stats[0] if backup_stats else 0,
                'total_size': backup_stats[1] if backup_stats and backup_stats[1] else 0,
                'total_size_mb': round((backup_stats[1] if backup_stats and backup_stats[1] else 0) / 1024 / 1024, 2),
                'webdav_backup_count': len(webdav_backups),
                'next_backup': self._get_next_backup_time()
            }

        except Exception as e:
            logger.error(f"获取备份状态失败: {str(e)}")
            return {
                'error': str(e),
                'last_backup': None,
                'backup_count': 0,
                'total_size': 0
            }

    def _get_next_backup_time(self) -> str:
        """获取下次备份时间"""
        now = datetime.now()
        next_backup = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if now >= next_backup:
            next_backup += timedelta(days=1)
        return next_backup.isoformat()

    async def manual_backup(self) -> Dict[str, Any]:
        """手动触发备份"""
        logger.info("执行手动备份")
        return await self.perform_backup()