"""WebDAV客户端功能测试"""
import pytest
import httpx
from unittest.mock import AsyncMock, Mock, patch
from app.core.webdav_client import WebDAVClient
from app.core.exceptions import (
    WebDAVAuthenticationError,
    WebDAVPermissionError,
    WebDAVNetworkError,
    WebDAVTimeoutError,
    WebDAVNotFoundError
)


@pytest.fixture
def webdav_client():
    """创建WebDAV客户端实例"""
    return WebDAVClient(
        url="http://localhost:10100/dav/",
        username="admin",
        password="adminlcs",
        base_path="onedrive_lcs"
    )


@pytest.fixture
def mock_httpx_client():
    """Mock httpx AsyncClient"""
    mock_client = AsyncMock()
    return mock_client


class TestWebDAVClientInitialization:
    """测试WebDAV客户端初始化"""

    def test_init_with_valid_params(self):
        """测试使用有效参数初始化"""
        client = WebDAVClient(
            url="http://localhost:10100/dav/",
            username="admin",
            password="test123"
        )
        assert client.url == "http://localhost:10100/dav/"
        assert client.username == "admin"
        assert client.password == "test123"

    def test_init_with_base_path(self):
        """测试使用基础路径初始化"""
        client = WebDAVClient(
            url="http://localhost:10100/dav/",
            username="admin",
            password="test123",
            base_path="files"
        )
        assert client.base_path == "files"

    def test_url_normalization(self):
        """测试URL标准化（自动添加尾部斜杠）"""
        client = WebDAVClient(
            url="http://localhost:10100/dav",  # 没有尾部斜杠
            username="admin",
            password="test123"
        )
        # URL应该被标准化为包含尾部斜杠
        assert client.url.endswith("/")


class TestWebDAVClientUpload:
    """测试WebDAV客户端上传功能"""

    @pytest.mark.asyncio
    async def test_upload_success(self, webdav_client, mock_httpx_client):
        """测试成功上传文件"""
        # Mock成功响应
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.headers = {"ETag": "abc123"}
        mock_httpx_client.put.return_value = mock_response

        with patch.object(webdav_client, '_client', mock_httpx_client):
            etag = await webdav_client.upload_file(
                local_path="/tmp/test.jpg",
                remote_path="files/test.jpg",
                content=b"test content"
            )

        assert etag == "abc123"
        mock_httpx_client.put.assert_called_once()

    @pytest.mark.asyncio
    async def test_upload_with_chinese_filename(self, webdav_client, mock_httpx_client):
        """测试上传中文文件名"""
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.headers = {"ETag": "def456"}
        mock_httpx_client.put.return_value = mock_response

        with patch.object(webdav_client, '_client', mock_httpx_client):
            etag = await webdav_client.upload_file(
                local_path="/tmp/测试图片.jpg",
                remote_path="files/测试图片.jpg",
                content=b"test content"
            )

        assert etag == "def456"
        # 验证URL被正确编码
        call_args = mock_httpx_client.put.call_args
        assert "files/" in str(call_args)

    @pytest.mark.asyncio
    async def test_upload_authentication_error(self, webdav_client, mock_httpx_client):
        """测试上传认证失败"""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_httpx_client.put.return_value = mock_response

        with patch.object(webdav_client, '_client', mock_httpx_client):
            with pytest.raises(WebDAVAuthenticationError):
                await webdav_client.upload_file(
                    local_path="/tmp/test.jpg",
                    remote_path="files/test.jpg",
                    content=b"test content"
                )

    @pytest.mark.asyncio
    async def test_upload_permission_error(self, webdav_client, mock_httpx_client):
        """测试上传权限错误"""
        mock_response = Mock()
        mock_response.status_code = 403
        mock_response.text = "Forbidden"
        mock_httpx_client.put.return_value = mock_response

        with patch.object(webdav_client, '_client', mock_httpx_client):
            with pytest.raises(WebDAVPermissionError):
                await webdav_client.upload_file(
                    local_path="/tmp/test.jpg",
                    remote_path="files/test.jpg",
                    content=b"test content"
                )

    @pytest.mark.asyncio
    async def test_upload_network_timeout(self, webdav_client, mock_httpx_client):
        """测试上传网络超时"""
        mock_httpx_client.put.side_effect = httpx.TimeoutException("Request timeout")

        with patch.object(webdav_client, '_client', mock_httpx_client):
            with pytest.raises(WebDAVTimeoutError):
                await webdav_client.upload_file(
                    local_path="/tmp/test.jpg",
                    remote_path="files/test.jpg",
                    content=b"test content"
                )


class TestWebDAVClientDownload:
    """测试WebDAV客户端下载功能"""

    @pytest.mark.asyncio
    async def test_download_success(self, webdav_client, mock_httpx_client):
        """测试成功下载文件"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"file content"
        mock_httpx_client.get.return_value = mock_response

        with patch.object(webdav_client, '_client', mock_httpx_client):
            content = await webdav_client.download_file("files/test.jpg")

        assert content == b"file content"
        mock_httpx_client.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_download_not_found(self, webdav_client, mock_httpx_client):
        """测试下载不存在的文件"""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"
        mock_httpx_client.get.return_value = mock_response

        with patch.object(webdav_client, '_client', mock_httpx_client):
            with pytest.raises(WebDAVNotFoundError):
                await webdav_client.download_file("files/nonexistent.jpg")

    @pytest.mark.asyncio
    async def test_download_chinese_filename(self, webdav_client, mock_httpx_client):
        """测试下载中文文件名"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"chinese file content"
        mock_httpx_client.get.return_value = mock_response

        with patch.object(webdav_client, '_client', mock_httpx_client):
            content = await webdav_client.download_file("files/中文文件.jpg")

        assert content == b"chinese file content"


class TestWebDAVClientList:
    """测试WebDAV客户端列表功能"""

    @pytest.mark.asyncio
    async def test_list_files_success(self, webdav_client, mock_httpx_client):
        """测试成功列出文件"""
        # Mock PROPFIND响应
        mock_response = Mock()
        mock_response.status_code = 207
        mock_response.text = """<?xml version="1.0"?>
<d:multistatus xmlns:d="DAV:">
    <d:response>
        <d:href>/dav/files/test1.jpg</d:href>
        <d:propstat>
            <d:prop>
                <d:displayname>test1.jpg</d:displayname>
                <d:getcontentlength>1024</d:getcontentlength>
                <d:getlastmodified>Mon, 27 Oct 2025 10:00:00 GMT</d:getlastmodified>
            </d:prop>
        </d:propstat>
    </d:response>
</d:multistatus>"""
        mock_httpx_client.request.return_value = mock_response

        with patch.object(webdav_client, '_client', mock_httpx_client):
            files = await webdav_client.list_files("files/")

        assert len(files) > 0
        assert any("test1.jpg" in f["href"] for f in files)

    @pytest.mark.asyncio
    async def test_list_files_empty_directory(self, webdav_client, mock_httpx_client):
        """测试列出空目录"""
        mock_response = Mock()
        mock_response.status_code = 207
        mock_response.text = """<?xml version="1.0"?>
<d:multistatus xmlns:d="DAV:">
    <d:response>
        <d:href>/dav/empty/</d:href>
    </d:response>
</d:multistatus>"""
        mock_httpx_client.request.return_value = mock_response

        with patch.object(webdav_client, '_client', mock_httpx_client):
            files = await webdav_client.list_files("empty/")

        # 应该只有目录本身，没有文件
        assert len(files) <= 1


class TestWebDAVClientDelete:
    """测试WebDAV客户端删除功能"""

    @pytest.mark.asyncio
    async def test_delete_file_success(self, webdav_client, mock_httpx_client):
        """测试成功删除文件"""
        mock_response = Mock()
        mock_response.status_code = 204
        mock_httpx_client.delete.return_value = mock_response

        with patch.object(webdav_client, '_client', mock_httpx_client):
            result = await webdav_client.delete_file("files/test.jpg")

        assert result is True
        mock_httpx_client.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_file_not_found(self, webdav_client, mock_httpx_client):
        """测试删除不存在的文件"""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"
        mock_httpx_client.delete.return_value = mock_response

        with patch.object(webdav_client, '_client', mock_httpx_client):
            with pytest.raises(WebDAVNotFoundError):
                await webdav_client.delete_file("files/nonexistent.jpg")


class TestWebDAVClientRetry:
    """测试WebDAV客户端重试机制"""

    @pytest.mark.asyncio
    async def test_upload_with_retry_success(self, webdav_client, mock_httpx_client):
        """测试上传失败后重试成功"""
        # 第一次失败（网络错误），第二次成功
        mock_response_fail = Mock()
        mock_response_fail.status_code = 500
        mock_response_fail.text = "Internal Server Error"

        mock_response_success = Mock()
        mock_response_success.status_code = 201
        mock_response_success.headers = {"ETag": "retry_success"}

        mock_httpx_client.put.side_effect = [mock_response_fail, mock_response_success]

        with patch.object(webdav_client, '_client', mock_httpx_client):
            # 应该在重试后成功
            etag = await webdav_client.upload_file(
                local_path="/tmp/test.jpg",
                remote_path="files/test.jpg",
                content=b"test content"
            )

        assert etag == "retry_success"
        # 验证调用了2次（1次失败+1次重试）
        assert mock_httpx_client.put.call_count == 2


class TestWebDAVClientHealthCheck:
    """测试WebDAV客户端健康检查"""

    @pytest.mark.asyncio
    async def test_health_check_success(self, webdav_client, mock_httpx_client):
        """测试健康检查成功"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_httpx_client.request.return_value = mock_response

        with patch.object(webdav_client, '_client', mock_httpx_client):
            is_healthy = await webdav_client.check_health()

        assert is_healthy is True

    @pytest.mark.asyncio
    async def test_health_check_failed(self, webdav_client, mock_httpx_client):
        """测试健康检查失败"""
        mock_httpx_client.request.side_effect = httpx.ConnectError("Connection refused")

        with patch.object(webdav_client, '_client', mock_httpx_client):
            is_healthy = await webdav_client.check_health()

        assert is_healthy is False
