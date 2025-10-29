"""
文件管理服务
混合存储策略实现
缓存管理、文件访问、清理策略
WebDAV故障降级处理
"""

import os
import json
import asyncio
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from urllib.parse import quote, unquote
import logging

from .config import get_settings
from .webdav_client import WebDAVClient
from .database import get_db_connection

logger = logging.getLogger(__name__)


class FileManager:
    """文件管理器，实现混合存储策略"""

    def __init__(self):
        self.settings = get_settings()
        self.webdav_client = WebDAVClient()

        # 确保必要的目录存在
        self._ensure_directories()

        # WebDAV状态
        self._webdav_available = False
        self._last_health_check = None

        # 待同步文件清单
        self._pending_sync_file = os.path.join(
            self.settings.TEMP_STORAGE_DIR,
            "pending_sync.json"
        )

        logger.info("文件管理器初始化完成")
        logger.info(f"缓存目录: {self.settings.CACHE_DIR}")
        logger.info(f"临时存储目录: {self.settings.TEMP_STORAGE_DIR}")
        logger.info(f"缓存保留天数: {self.settings.CACHE_DAYS}")

    def _ensure_directories(self):
        """确保必要的目录存在"""
        directories = [
            self.settings.CACHE_DIR,
            self.settings.TEMP_STORAGE_DIR,
            os.path.join(self.settings.CACHE_DIR, "files"),
            self.settings.LOCAL_STORAGE_PATH
        ]

        for directory in directories:
            try:
                os.makedirs(directory, exist_ok=True)
                logger.debug(f"确保目录存在: {directory}")
            except Exception as e:
                logger.error(f"创建目录失败 {directory}: {str(e)}")
                raise

    def _get_cache_path(self, webdav_path: str) -> str:
        """获取本地缓存路径"""
        # 移除开头的files/前缀
        if webdav_path.startswith('files/'):
            relative_path = webdav_path[6:]  # 去掉'files/'
        else:
            relative_path = webdav_path.lstrip('/')

        return os.path.join(self.settings.CACHE_DIR, relative_path)

    def _get_temp_path(self, filename: str) -> str:
        """获取临时存储路径"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        # 添加时间戳避免文件名冲突
        name, ext = os.path.splitext(filename)
        temp_filename = f"{timestamp}_{name}{ext}"
        return os.path.join(self.settings.TEMP_STORAGE_DIR, temp_filename)

    def _generate_webdav_path(self, filename: str) -> str:
        """生成WebDAV文件路径"""
        now = datetime.now()
        # 按年/月/日组织文件
        date_path = now.strftime('%Y/%m/%d')
        return f"files/{date_path}/{filename}"

    def _is_cache_valid(self, cache_path: str) -> bool:
        """检查缓存是否有效（7天内）"""
        if not os.path.exists(cache_path):
            return False

        try:
            # 检查文件修改时间
            mtime = os.path.getmtime(cache_path)
            file_time = datetime.fromtimestamp(mtime)
            expiry_time = file_time + timedelta(days=self.settings.CACHE_DAYS)

            return datetime.now() < expiry_time
        except Exception as e:
            logger.error(f"检查缓存有效性失败 {cache_path}: {str(e)}")
            return False

    def _load_pending_sync(self) -> Dict[str, Any]:
        """加载待同步文件清单"""
        if not os.path.exists(self._pending_sync_file):
            return {'files': [], 'last_sync': None}

        try:
            with open(self._pending_sync_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载待同步清单失败: {str(e)}")
            return {'files': [], 'last_sync': None}

    def _save_pending_sync(self, data: Dict[str, Any]):
        """保存待同步文件清单"""
        try:
            os.makedirs(os.path.dirname(self._pending_sync_file), exist_ok=True)
            with open(self._pending_sync_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存待同步清单失败: {str(e)}")

    async def check_webdav_health(self) -> bool:
        """检查WebDAV健康状态"""
        try:
            now = datetime.now()

            # 如果距离上次检查时间太短，直接返回缓存结果
            # 使用total_seconds()获取完整时间差(包括天数)
            if (self._last_health_check and
                (now - self._last_health_check).total_seconds() < self.settings.HEALTH_CHECK_INTERVAL):
                return self._webdav_available

            is_healthy = await self.webdav_client.health_check()
            self._webdav_available = is_healthy
            self._last_health_check = now

            if is_healthy:
                logger.debug("WebDAV服务可用")
            else:
                logger.warning("WebDAV服务不可用")

            return is_healthy

        except Exception as e:
            logger.error(f"WebDAV健康检查失败: {str(e)}")
            self._webdav_available = False
            return False

    async def save_file(self, file_content: bytes, filename: str) -> Dict[str, Any]:
        """保存文件（WebDAV + 本地缓存）"""
        try:
            webdav_path = self._generate_webdav_path(filename)
            file_size = len(file_content)

            logger.info(f"开始保存文件: {filename} ({file_size} bytes)")

            # 检查WebDAV可用性
            webdav_available = await self.check_webdav_health()

            result = {
                'filename': filename,
                'webdav_path': webdav_path,
                'file_size': file_size,
                'upload_time': datetime.now().isoformat(),
                'success': False,
                'error': None
            }

            if webdav_available:
                # WebDAV可用，直接上传
                try:
                    # 创建临时文件用于上传
                    temp_path = self._get_temp_path(filename)
                    with open(temp_path, 'wb') as f:
                        f.write(file_content)

                    # 上传到WebDAV
                    upload_result = await self.webdav_client.upload_file(
                        temp_path, webdav_path
                    )

                    if upload_result['success']:
                        # 上传成功，写入缓存
                        cache_path = self._get_cache_path(webdav_path)
                        await self._write_cache(cache_path, file_content)

                        result.update({
                            'success': True,
                            'local_cache_path': cache_path,
                            'is_cached': True,
                            'webdav_etag': upload_result.get('etag'),
                            'is_synced': True
                        })

                        logger.info(f"文件保存成功: {webdav_path}")
                    else:
                        # WebDAV上传失败，降级到临时存储
                        logger.warning(f"WebDAV上传失败，降级到临时存储: {upload_result['error']}")
                        await self._save_to_temp_storage(file_content, filename, webdav_path, result)

                    # 清理临时文件
                    if os.path.exists(temp_path):
                        os.remove(temp_path)

                except Exception as e:
                    logger.error(f"文件保存过程中出错: {str(e)}")
                    await self._save_to_temp_storage(file_content, filename, webdav_path, result)

            else:
                # WebDAV不可用，直接降级到临时存储
                logger.warning("WebDAV不可用，文件降级到临时存储")
                await self._save_to_temp_storage(file_content, filename, webdav_path, result)

            return result

        except Exception as e:
            error_msg = f"保存文件失败: {str(e)}"
            logger.error(error_msg)
            return {
                'filename': filename,
                'success': False,
                'error': error_msg
            }

    async def _write_cache(self, cache_path: str, file_content: bytes):
        """写入本地缓存"""
        try:
            # 确保缓存目录存在
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)

            # 写入缓存文件
            with open(cache_path, 'wb') as f:
                f.write(file_content)

            logger.debug(f"缓存文件写入成功: {cache_path}")

        except Exception as e:
            logger.error(f"写入缓存失败 {cache_path}: {str(e)}")
            # 缓存写入失败不应该影响主流程

    async def _save_to_temp_storage(self, file_content: bytes, filename: str, webdav_path: str, result: Dict[str, Any]):
        """保存到临时存储（降级处理）"""
        try:
            temp_path = self._get_temp_path(filename)

            # 写入临时文件
            with open(temp_path, 'wb') as f:
                f.write(file_content)

            # 添加到待同步清单
            pending_sync = self._load_pending_sync()
            pending_sync['files'].append({
                'temp_path': temp_path,
                'filename': filename,
                'webdav_path': webdav_path,
                'created_time': datetime.now().isoformat()
            })
            self._save_pending_sync(pending_sync)

            result.update({
                'success': True,  # 降级存储也认为是成功的
                'local_cache_path': temp_path,
                'is_cached': False,
                'is_synced': False,
                'storage_type': 'temp'
            })

            logger.info(f"文件已降级到临时存储: {temp_path}")

        except Exception as e:
            logger.error(f"临时存储保存失败: {str(e)}")
            result['error'] = f"临时存储保存失败: {str(e)}"

    async def get_file(self, webdav_path: str, max_retries: int = 3) -> bytes:
        """
        获取文件内容（优先从缓存,支持WebDAV重试）

        Args:
            webdav_path: WebDAV文件路径
            max_retries: 最大重试次数,默认3次

        Returns:
            文件内容(bytes)

        Raises:
            Exception: 当所有重试都失败时
        """
        try:
            logger.debug(f"获取文件: {webdav_path}")

            # 检查缓存
            cache_path = self._get_cache_path(webdav_path)
            if self._is_cache_valid(cache_path):
                logger.debug(f"缓存命中: {cache_path}")
                with open(cache_path, 'rb') as f:
                    content = f.read()

                # 更新访问时间
                os.utime(cache_path)
                return content

            # 缓存未命中，从WebDAV下载（带重试机制）
            logger.debug(f"缓存未命中，从WebDAV下载: {webdav_path}")

            last_error = None
            for attempt in range(1, max_retries + 1):
                try:
                    content = await self.webdav_client.download_file(webdav_path)

                    # 下载成功，尝试写入缓存
                    try:
                        await self._write_cache(cache_path, content)
                        logger.debug(f"文件已缓存: {cache_path}")
                    except Exception as e:
                        logger.warning(f"缓存写入失败: {str(e)}")

                    # 如果有重试，记录成功信息
                    if attempt > 1:
                        logger.info(f"WebDAV下载成功 (第{attempt}次尝试): {webdav_path}")

                    return content

                except Exception as e:
                    last_error = e
                    if attempt < max_retries:
                        # 不是最后一次尝试，记录警告并重试
                        logger.warning(
                            f"WebDAV下载失败 (第{attempt}/{max_retries}次): {webdav_path} - {str(e)}, "
                            f"1秒后重试..."
                        )
                        await asyncio.sleep(1)  # 等待1秒后重试
                    else:
                        # 最后一次尝试也失败了
                        logger.error(
                            f"WebDAV下载失败 (已重试{max_retries}次): {webdav_path} - {str(e)}"
                        )

            # 所有重试都失败
            error_msg = f"获取文件失败 (已重试{max_retries}次): {str(last_error)}"
            raise Exception(error_msg)

        except Exception as e:
            error_msg = f"获取文件失败: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg)

    async def cleanup_cache(self) -> Dict[str, int]:
        """清理过期缓存文件"""
        try:
            logger.info("开始清理缓存文件")

            stats = {
                'total_files': 0,
                'deleted_files': 0,
                'freed_space': 0
            }

            cache_dir = Path(self.settings.CACHE_DIR)
            if not cache_dir.exists():
                logger.info("缓存目录不存在，跳过清理")
                return stats

            expiry_time = datetime.now() - timedelta(days=self.settings.CACHE_DAYS)

            # 遍历缓存目录
            for file_path in cache_dir.rglob('*'):
                if not file_path.is_file():
                    continue

                stats['total_files'] += 1

                try:
                    # 检查文件修改时间
                    mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                    if mtime < expiry_time:
                        file_size = file_path.stat().st_size
                        file_path.unlink()

                        stats['deleted_files'] += 1
                        stats['freed_space'] += file_size

                        logger.debug(f"删除过期缓存文件: {file_path}")

                except Exception as e:
                    logger.error(f"处理缓存文件失败 {file_path}: {str(e)}")

            logger.info(f"缓存清理完成: 删除{stats['deleted_files']}个文件，释放{stats['freed_space']}字节")
            return stats

        except Exception as e:
            logger.error(f"缓存清理失败: {str(e)}")
            return {'error': str(e)}

    async def sync_pending_files(self) -> Dict[str, Any]:
        """同步待同步文件到WebDAV"""
        try:
            logger.info("开始同步待同步文件")

            # 检查WebDAV可用性
            if not await self.check_webdav_health():
                return {
                    'success': False,
                    'error': 'WebDAV服务不可用，跳过同步',
                    'synced_count': 0,
                    'failed_count': 0
                }

            pending_sync = self._load_pending_sync()
            files = pending_sync.get('files', [])

            if not files:
                return {
                    'success': True,
                    'message': '没有待同步文件',
                    'synced_count': 0,
                    'failed_count': 0
                }

            stats = {
                'success': True,
                'synced_count': 0,
                'failed_count': 0,
                'errors': []
            }

            remaining_files = []

            for file_info in files:
                try:
                    temp_path = file_info['temp_path']
                    filename = file_info['filename']
                    webdav_path = file_info['webdav_path']

                    # 检查临时文件是否存在
                    if not os.path.exists(temp_path):
                        logger.warning(f"临时文件不存在，跳过: {temp_path}")
                        continue

                    # 上传到WebDAV
                    upload_result = await self.webdav_client.upload_file(
                        temp_path, webdav_path
                    )

                    if upload_result['success']:
                        # 同步成功，删除临时文件
                        os.remove(temp_path)
                        stats['synced_count'] += 1
                        logger.info(f"文件同步成功: {webdav_path}")
                    else:
                        # 同步失败，保留在清单中
                        remaining_files.append(file_info)
                        stats['failed_count'] += 1
                        stats['errors'].append({
                            'filename': filename,
                            'error': upload_result.get('error', '未知错误')
                        })
                        logger.error(f"文件同步失败: {filename} - {upload_result.get('error')}")

                except Exception as e:
                    remaining_files.append(file_info)
                    stats['failed_count'] += 1
                    stats['errors'].append({
                        'filename': file_info.get('filename', 'unknown'),
                        'error': str(e)
                    })
                    logger.error(f"同步文件异常: {str(e)}")

            # 更新待同步清单
            pending_sync['files'] = remaining_files
            pending_sync['last_sync'] = datetime.now().isoformat()
            self._save_pending_sync(pending_sync)

            logger.info(f"同步完成: 成功{stats['synced_count']}，失败{stats['failed_count']}")
            return stats

        except Exception as e:
            error_msg = f"同步待同步文件失败: {str(e)}"
            logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg,
                'synced_count': 0,
                'failed_count': 0
            }

    async def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        try:
            cache_dir = Path(self.settings.CACHE_DIR)
            if not cache_dir.exists():
                return {
                    'total_files': 0,
                    'total_size': 0,
                    'cache_dir': str(cache_dir)
                }

            total_files = 0
            total_size = 0

            for file_path in cache_dir.rglob('*'):
                if file_path.is_file():
                    total_files += 1
                    total_size += file_path.stat().st_size

            return {
                'total_files': total_files,
                'total_size': total_size,
                'total_size_mb': round(total_size / 1024 / 1024, 2),
                'cache_dir': str(cache_dir)
            }

        except Exception as e:
            logger.error(f"获取缓存统计失败: {str(e)}")
            return {
                'error': str(e),
                'total_files': 0,
                'total_size': 0
            }

    async def get_pending_sync_count(self) -> int:
        """获取待同步文件数量"""
        try:
            pending_sync = self._load_pending_sync()
            return len(pending_sync.get('files', []))
        except Exception as e:
            logger.error(f"获取待同步文件数量失败: {str(e)}")
            return 0

    async def is_webdav_available(self) -> bool:
        """检查WebDAV是否可用"""
        return await self.check_webdav_health()