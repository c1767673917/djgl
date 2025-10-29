"""
WebDAV异步客户端实现
支持PROPFIND, GET, PUT, DELETE, MKCOL方法
包含重试机制、错误处理、进度回调
"""

import os
import asyncio
import base64
import xml.etree.ElementTree as ET
from urllib.parse import quote, unquote
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime
import logging

import httpx
from .config import get_settings
from .exceptions import (
    WebDAVError, WebDAVAuthenticationError, WebDAVPermissionError,
    WebDAVNotFoundError, WebDAVTimeoutError, WebDAVNetworkError,
    WebDAVServerError
)
from .logging_config import log_async_function_call, get_logger

logger = get_logger(__name__)


class WebDAVClient:
    """WebDAV异步客户端"""

    def __init__(self):
        self.settings = get_settings()
        self.base_url = self.settings.WEBDAV_URL.rstrip('/')
        self.base_path = self.settings.WEBDAV_BASE_PATH.strip('/')
        self.auth_string = base64.b64encode(
            f"{self.settings.WEBDAV_USERNAME}:{self.settings.WEBDAV_PASSWORD}"
            .encode('utf-8')
        ).decode('utf-8')

        # HTTP客户端配置
        self.timeout = httpx.Timeout(self.settings.WEBDAV_TIMEOUT)
        self.retry_count = self.settings.WEBDAV_RETRY_COUNT
        self.retry_delay = self.settings.WEBDAV_RETRY_DELAY

        logger.info(f"WebDAV客户端初始化完成: {self.base_url}")
        logger.debug(f"基础路径: {self.base_path}")
        logger.debug(f"超时设置: {self.settings.WEBDAV_TIMEOUT}秒")
        logger.debug(f"重试次数: {self.settings.WEBDAV_RETRY_COUNT}")

    def _get_full_url(self, path: str) -> str:
        """获取完整的WebDAV URL"""
        # 确保路径以/开头
        if not path.startswith('/'):
            path = '/' + path

        # 添加base_path
        if self.base_path:
            full_path = f"/{self.base_path}{path}"
        else:
            full_path = path

        # URL编码路径
        encoded_path = quote(full_path, safe='/')

        return f"{self.base_url}{encoded_path}"

    def _get_headers(self, method: str = None, content_length: int = None) -> Dict[str, str]:
        """获取请求头"""
        headers = {
            'Authorization': f'Basic {self.auth_string}',
            'User-Agent': f'UploadManager/{self.settings.APP_VERSION}',
        }

        if method:
            headers['X-HTTP-Method-Override'] = method

        if content_length is not None:
            headers['Content-Length'] = str(content_length)

        return headers

    async def _make_request(
        self,
        method: str,
        path: str,
        content: Optional[bytes] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> httpx.Response:
        """发起HTTP请求，包含重试机制"""
        url = self._get_full_url(path)
        request_headers = self._get_headers()

        if headers:
            request_headers.update(headers)

        last_error = None

        for attempt in range(self.retry_count + 1):
            try:
                if self.settings.WEBDAV_DEBUG:
                    logger.debug(f"WebDAV请求 [{attempt + 1}/{self.retry_count + 1}]: {method} {url}")

                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.request(
                        method=method,
                        url=url,
                        content=content,
                        headers=request_headers
                    )

                if self.settings.WEBDAV_DEBUG:
                    logger.debug(f"WebDAV响应: {response.status_code}")

                # 检查响应状态
                # 207 Multi-Status用于PROPFIND响应
                if response.status_code in [200, 201, 204, 207]:
                    return response
                elif response.status_code == 401:
                    raise WebDAVAuthenticationError()
                elif response.status_code == 403:
                    raise WebDAVPermissionError()
                elif response.status_code == 404:
                    raise WebDAVNotFoundError(f"WebDAV路径不存在: {path}", path=path)
                elif response.status_code >= 500:
                    # 服务器错误，可以重试
                    last_error = f"WebDAV服务器错误: {response.status_code}"
                    if attempt < self.retry_count:
                        logger.warning(f"{last_error}，{self.retry_delay}秒后重试...")
                        await asyncio.sleep(self.retry_delay)
                        continue
                    raise WebDAVServerError(last_error, response.status_code)
                else:
                    # 其他错误，不重试
                    raise WebDAVError(f"WebDAV请求失败: {response.status_code} - {response.text}",
                                    status_code=response.status_code)

            except httpx.TimeoutException:
                last_error = "WebDAV请求超时"
                if attempt < self.retry_count:
                    logger.warning(f"{last_error}，{self.retry_delay}秒后重试...")
                    await asyncio.sleep(self.retry_delay)
                    continue
                raise WebDAVTimeoutError(last_error)
            except httpx.RequestError as e:
                last_error = f"WebDAV网络错误: {str(e)}"
                if attempt < self.retry_count:
                    logger.warning(f"{last_error}，{self.retry_delay}秒后重试...")
                    await asyncio.sleep(self.retry_delay)
                    continue
                raise WebDAVNetworkError(last_error, original_error=e)
            except Exception as e:
                # 如果是我们自定义的WebDAV异常，直接抛出
                if isinstance(e, (WebDAVAuthenticationError, WebDAVPermissionError, WebDAVNotFoundError)):
                    raise e
                if isinstance(e, WebDAVError):
                    status_code = getattr(e, "status_code", None)
                    if status_code in (405, 409):
                        # 避免对已存在的目录重复重试
                        raise e
                elif "认证失败" in str(e) or "权限不足" in str(e):
                    # 兼容旧的错误消息
                    raise WebDAVAuthenticationError(str(e))
                else:
                    last_error = str(e)
                    if attempt < self.retry_count:
                        logger.warning(f"{last_error}，{self.retry_delay}秒后重试...")
                        await asyncio.sleep(self.retry_delay)
                        continue
                    raise WebDAVError(last_error)

        # 如果所有重试都失败了
        raise WebDAVError(last_error or "WebDAV请求失败")

    @log_async_function_call()
    async def health_check(self) -> bool:
        """检查WebDAV服务健康状态"""
        try:
            logger.debug("执行WebDAV健康检查...")
            # 使用PROPFIND方法检查根目录,更兼容各种WebDAV服务器
            # 许多WebDAV服务器(Nextcloud, Apache mod_dav)不支持根路径的HEAD请求
            headers = {
                'Depth': '0',
                'Content-Type': 'application/xml; charset=utf-8'
            }
            propfind_xml = '''<?xml version="1.0" encoding="utf-8" ?>
<D:propfind xmlns:D="DAV:">
    <D:prop>
        <D:resourcetype/>
    </D:prop>
</D:propfind>'''

            response = await self._make_request(
                'PROPFIND',
                '/',
                content=propfind_xml.encode('utf-8'),
                headers=headers
            )
            # PROPFIND成功返回207 Multi-Status
            is_healthy = response.status_code in [200, 207]

            if is_healthy:
                logger.debug("WebDAV健康检查通过")
            else:
                logger.warning(f"WebDAV健康检查失败: {response.status_code}")

            return is_healthy
        except Exception as e:
            logger.error(f"WebDAV健康检查异常: {str(e)}")
            return False

    @log_async_function_call()
    async def upload_file(
        self,
        local_path: str,
        webdav_path: str,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> Dict[str, Any]:
        """上传文件到WebDAV"""
        try:
            # 检查本地文件是否存在
            if not os.path.exists(local_path):
                raise Exception(f"本地文件不存在: {local_path}")

            file_size = os.path.getsize(local_path)
            logger.info(f"开始上传文件: {local_path} -> {webdav_path} ({file_size} bytes)")

            # 确保目标目录存在
            directory = os.path.dirname(webdav_path)
            if directory and directory != '/':
                await self.create_directory(directory)

            # 读取文件内容
            with open(local_path, 'rb') as f:
                file_content = f.read()

            # 上传文件
            response = await self._make_request(
                'PUT',
                webdav_path,
                content=file_content
            )

            # 获取ETag
            etag = response.headers.get('ETag', '').strip('"')

            result = {
                'success': True,
                'webdav_path': webdav_path,
                'file_size': file_size,
                'etag': etag,
                'upload_time': datetime.now().isoformat()
            }

            logger.info(f"文件上传成功: {webdav_path}")
            return result

        except Exception as e:
            error_msg = f"文件上传失败: {str(e)}"
            logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg,
                'webdav_path': webdav_path
            }

    @log_async_function_call()
    async def download_file(self, webdav_path: str) -> bytes:
        """从WebDAV下载文件"""
        try:
            logger.debug(f"开始下载文件: {webdav_path}")

            response = await self._make_request('GET', webdav_path)
            file_content = response.content

            logger.debug(f"文件下载成功: {webdav_path} ({len(file_content)} bytes)")
            return file_content

        except Exception as e:
            error_msg = f"文件下载失败: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg)

    async def delete_file(self, webdav_path: str) -> bool:
        """删除WebDAV文件"""
        try:
            logger.debug(f"开始删除文件: {webdav_path}")

            await self._make_request('DELETE', webdav_path)

            logger.debug(f"文件删除成功: {webdav_path}")
            return True

        except Exception as e:
            error_msg = f"文件删除失败: {str(e)}"
            logger.error(error_msg)
            return False

    async def create_directory(self, path: str) -> bool:
        """创建目录"""
        try:
            if not path or path == '/':
                return True

            logger.debug(f"创建目录: {path}")

            # 确保路径以/开头
            if not path.startswith('/'):
                path = '/' + path

            # 移除末尾的/
            path = path.rstrip('/')

            # 递归创建父目录
            parent_path = os.path.dirname(path)
            if parent_path and parent_path != '/':
                await self.create_directory(parent_path)

            # 创建当前目录（WebDAV部分服务需要以/结尾）
            mkcol_path = path if path.endswith('/') else f"{path}/"
            await self._make_request('MKCOL', mkcol_path)

            logger.debug(f"目录创建成功: {mkcol_path}")
            return True

        except WebDAVError as e:
            if e.status_code == 405:
                # 目录已存在
                logger.debug(f"目录已存在: {path}")
                return True
            error_msg = f"目录创建失败: {str(e)}"
            logger.error(error_msg)
            return False
        except Exception as e:
            error_msg = f"目录创建失败: {str(e)}"
            logger.error(error_msg)
            return False

    async def list_files(self, path: str = '/') -> List[Dict[str, Any]]:
        """列出目录中的文件"""
        try:
            logger.debug(f"列出目录内容: {path}")

            # 确保路径以/开头
            if not path.startswith('/'):
                path = '/' + path

            # 发送PROPFIND请求
            headers = {
                'Depth': '1',
                'Content-Type': 'application/xml; charset=utf-8'
            }

            propfind_xml = '''<?xml version="1.0" encoding="utf-8" ?>
<D:propfind xmlns:D="DAV:">
    <D:prop>
        <D:displayname/>
        <D:getcontentlength/>
        <D:getlastmodified/>
        <D:resourcetype/>
        <D:getetag/>
    </D:prop>
</D:propfind>'''

            response = await self._make_request(
                'PROPFIND',
                path,
                content=propfind_xml.encode('utf-8'),
                headers=headers
            )

            # 解析XML响应
            root = ET.fromstring(response.content)
            files = []

            # 定义命名空间
            namespaces = {'D': 'DAV:'}

            for response_elem in root.findall('.//D:response', namespaces):
                # 获取路径
                href_elem = response_elem.find('D:href', namespaces)
                if href_elem is None:
                    continue

                href = unquote(href_elem.text)

                # 跳过根目录
                if href == path or href == path.rstrip('/'):
                    continue

                # 获取文件名
                if href.endswith('/'):
                    name = os.path.basename(href.rstrip('/'))
                    is_directory = True
                else:
                    name = os.path.basename(href)
                    is_directory = False

                # 获取属性
                props = response_elem.find('D:propstat/D:prop', namespaces)
                if props is None:
                    continue

                file_info = {
                    'name': name,
                    'path': href,
                    'is_directory': is_directory
                }

                # 获取文件大小
                size_elem = props.find('D:getcontentlength', namespaces)
                if size_elem is not None:
                    file_info['size'] = int(size_elem.text)

                # 获取最后修改时间
                modified_elem = props.find('D:getlastmodified', namespaces)
                if modified_elem is not None:
                    file_info['modified'] = modified_elem.text

                # 获取ETag
                etag_elem = props.find('D:getetag', namespaces)
                if etag_elem is not None:
                    file_info['etag'] = etag_elem.text.strip('"')

                files.append(file_info)

            logger.debug(f"列出目录完成，共{len(files)}个项目")
            return files

        except Exception as e:
            error_msg = f"列出目录失败: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg)

    async def file_exists(self, webdav_path: str) -> bool:
        """检查文件是否存在"""
        try:
            await self._make_request('HEAD', webdav_path)
            return True
        except Exception as e:
            if "不存在" in str(e) or "404" in str(e):
                return False
            raise e

    async def get_file_info(self, webdav_path: str) -> Optional[Dict[str, Any]]:
        """获取文件信息"""
        try:
            files = await self.list_files(os.path.dirname(webdav_path))
            for file_info in files:
                if file_info['path'] == webdav_path:
                    return file_info
            return None
        except Exception as e:
            logger.error(f"获取文件信息失败: {str(e)}")
            return None
