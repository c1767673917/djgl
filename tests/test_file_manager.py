"""文件管理器功能测试"""
import pytest
import os
import tempfile
from datetime import timedelta
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from app.core.file_manager import FileManager
from app.core.exceptions import WebDAVNetworkError
from app.core.timezone import get_beijing_now, get_beijing_now_naive_iso


@pytest.fixture
def temp_cache_dir():
    """创建临时缓存目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def temp_storage_dir():
    """创建临时存储目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def file_manager(temp_cache_dir, temp_storage_dir):
    """创建文件管理器实例"""
    return FileManager(
        cache_dir=temp_cache_dir,
        temp_storage_dir=temp_storage_dir,
        cache_days=7
    )


@pytest.fixture
def mock_webdav_client():
    """Mock WebDAV客户端"""
    mock_client = AsyncMock()
    mock_client.check_health.return_value = True
    mock_client.upload_file.return_value = "mock_etag"
    mock_client.download_file.return_value = b"mock file content"
    return mock_client


class TestFileManagerInitialization:
    """测试文件管理器初始化"""

    def test_init_with_valid_params(self, temp_cache_dir, temp_storage_dir):
        """测试使用有效参数初始化"""
        manager = FileManager(
            cache_dir=temp_cache_dir,
            temp_storage_dir=temp_storage_dir,
            cache_days=7
        )
        assert manager.cache_dir == temp_cache_dir
        assert manager.temp_storage_dir == temp_storage_dir
        assert manager.cache_days == 7

    def test_cache_directory_creation(self, temp_storage_dir):
        """测试缓存目录自动创建"""
        cache_path = os.path.join(temp_storage_dir, "new_cache")
        manager = FileManager(
            cache_dir=cache_path,
            temp_storage_dir=temp_storage_dir
        )
        # 缓存目录应该被创建
        assert os.path.exists(cache_path)


class TestFileManagerUpload:
    """测试文件管理器上传功能"""

    @pytest.mark.asyncio
    async def test_upload_to_webdav_success(self, file_manager, mock_webdav_client):
        """测试成功上传到WebDAV"""
        with patch.object(file_manager, 'webdav_client', mock_webdav_client):
            result = await file_manager.upload_file(
                local_path="/tmp/test.jpg",
                remote_path="files/test.jpg",
                content=b"test content"
            )

        assert result["success"] is True
        assert result["webdav_uploaded"] is True
        assert result["cached"] is True
        mock_webdav_client.upload_file.assert_called_once()

    @pytest.mark.asyncio
    async def test_upload_webdav_unavailable(self, file_manager, mock_webdav_client, temp_storage_dir):
        """测试WebDAV不可用时降级到临时存储"""
        # Mock WebDAV不可用
        mock_webdav_client.check_health.return_value = False
        mock_webdav_client.upload_file.side_effect = WebDAVNetworkError("Connection failed")

        with patch.object(file_manager, 'webdav_client', mock_webdav_client):
            with patch.object(file_manager, 'webdav_available', False):
                result = await file_manager.upload_file(
                    local_path="/tmp/test.jpg",
                    remote_path="files/test.jpg",
                    content=b"test content"
                )

        assert result["success"] is True
        assert result["webdav_uploaded"] is False
        assert result["degraded"] is True
        # 验证文件被保存到临时存储
        assert result.get("temp_path") is not None

    @pytest.mark.asyncio
    async def test_upload_with_cache(self, file_manager, mock_webdav_client, temp_cache_dir):
        """测试上传时写入本地缓存"""
        with patch.object(file_manager, 'webdav_client', mock_webdav_client):
            result = await file_manager.upload_file(
                local_path="/tmp/test.jpg",
                remote_path="files/test.jpg",
                content=b"test content",
                enable_cache=True
            )

        assert result["cached"] is True
        # 验证缓存文件存在
        cache_path = os.path.join(temp_cache_dir, "files", "test.jpg")
        assert os.path.exists(cache_path)
        with open(cache_path, 'rb') as f:
            assert f.read() == b"test content"


class TestFileManagerDownload:
    """测试文件管理器下载功能"""

    @pytest.mark.asyncio
    async def test_download_from_cache_hit(self, file_manager, mock_webdav_client, temp_cache_dir):
        """测试从缓存命中下载"""
        # 预先创建缓存文件
        cache_path = os.path.join(temp_cache_dir, "files")
        os.makedirs(cache_path, exist_ok=True)
        cached_file = os.path.join(cache_path, "test.jpg")
        with open(cached_file, 'wb') as f:
            f.write(b"cached content")

        # 设置文件为7天内（缓存有效）
        current_ts = get_beijing_now().timestamp()
        os.utime(cached_file, (current_ts, current_ts))

        with patch.object(file_manager, 'webdav_client', mock_webdav_client):
            content = await file_manager.download_file("files/test.jpg")

        assert content == b"cached content"
        # WebDAV客户端不应该被调用
        mock_webdav_client.download_file.assert_not_called()

    @pytest.mark.asyncio
    async def test_download_from_cache_miss(self, file_manager, mock_webdav_client):
        """测试缓存未命中，从WebDAV下载"""
        mock_webdav_client.download_file.return_value = b"webdav content"

        with patch.object(file_manager, 'webdav_client', mock_webdav_client):
            content = await file_manager.download_file("files/test.jpg")

        assert content == b"webdav content"
        mock_webdav_client.download_file.assert_called_once_with("files/test.jpg")

    @pytest.mark.asyncio
    async def test_download_cache_expired(self, file_manager, mock_webdav_client, temp_cache_dir):
        """测试缓存过期，从WebDAV重新下载"""
        # 创建过期的缓存文件（8天前）
        cache_path = os.path.join(temp_cache_dir, "files")
        os.makedirs(cache_path, exist_ok=True)
        cached_file = os.path.join(cache_path, "test.jpg")
        with open(cached_file, 'wb') as f:
            f.write(b"old cached content")

        # 设置文件修改时间为8天前
        old_time = (get_beijing_now() - timedelta(days=8)).timestamp()
        os.utime(cached_file, (old_time, old_time))

        mock_webdav_client.download_file.return_value = b"fresh webdav content"

        with patch.object(file_manager, 'webdav_client', mock_webdav_client):
            content = await file_manager.download_file("files/test.jpg")

        # 应该从WebDAV下载新内容
        assert content == b"fresh webdav content"
        mock_webdav_client.download_file.assert_called_once()


class TestFileManagerCacheManagement:
    """测试文件管理器缓存管理"""

    @pytest.mark.asyncio
    async def test_cache_cleanup_expired_files(self, file_manager, temp_cache_dir):
        """测试清理过期缓存文件"""
        # 创建测试缓存文件
        cache_path = os.path.join(temp_cache_dir, "files")
        os.makedirs(cache_path, exist_ok=True)

        # 有效缓存（3天前）
        valid_file = os.path.join(cache_path, "valid.jpg")
        with open(valid_file, 'wb') as f:
            f.write(b"valid")
        valid_time = (get_beijing_now() - timedelta(days=3)).timestamp()
        os.utime(valid_file, (valid_time, valid_time))

        # 过期缓存（8天前）
        expired_file = os.path.join(cache_path, "expired.jpg")
        with open(expired_file, 'wb') as f:
            f.write(b"expired")
        expired_time = (get_beijing_now() - timedelta(days=8)).timestamp()
        os.utime(expired_file, (expired_time, expired_time))

        # 执行清理
        result = await file_manager.cleanup_expired_cache()

        # 验证过期文件被删除，有效文件保留
        assert not os.path.exists(expired_file)
        assert os.path.exists(valid_file)
        assert result["deleted_count"] > 0

    @pytest.mark.asyncio
    async def test_get_cache_stats(self, file_manager, temp_cache_dir):
        """测试获取缓存统计信息"""
        # 创建测试缓存文件
        cache_path = os.path.join(temp_cache_dir, "files")
        os.makedirs(cache_path, exist_ok=True)

        for i in range(3):
            test_file = os.path.join(cache_path, f"test{i}.jpg")
            with open(test_file, 'wb') as f:
                f.write(b"x" * 1024)  # 1KB

        stats = await file_manager.get_cache_stats()

        assert stats["file_count"] == 3
        assert stats["total_size"] == 3 * 1024
        assert stats["cache_dir"] == temp_cache_dir


class TestFileManagerSyncMechanism:
    """测试文件管理器同步机制"""

    @pytest.mark.asyncio
    async def test_sync_pending_files_success(self, file_manager, mock_webdav_client, temp_storage_dir):
        """测试成功同步待同步文件"""
        # 创建待同步文件
        pending_file = os.path.join(temp_storage_dir, "pending_test.jpg")
        with open(pending_file, 'wb') as f:
            f.write(b"pending content")

        # Mock pending sync list
        pending_list = [
            {
                "local_path": pending_file,
                "remote_path": "files/pending_test.jpg",
                "timestamp": get_beijing_now_naive_iso()
            }
        ]

        with patch.object(file_manager, 'webdav_client', mock_webdav_client):
            with patch.object(file_manager, '_load_pending_sync_list', return_value=pending_list):
                with patch.object(file_manager, '_save_pending_sync_list') as mock_save:
                    result = await file_manager.sync_pending_files()

        assert result["synced_count"] > 0
        assert result["failed_count"] == 0
        mock_webdav_client.upload_file.assert_called()

    @pytest.mark.asyncio
    async def test_add_to_pending_sync(self, file_manager):
        """测试添加文件到待同步列表"""
        with patch.object(file_manager, '_save_pending_sync_list') as mock_save:
            await file_manager.add_to_pending_sync(
                local_path="/tmp/test.jpg",
                remote_path="files/test.jpg"
            )

        mock_save.assert_called_once()


class TestFileManagerHealthCheck:
    """测试文件管理器健康检查"""

    @pytest.mark.asyncio
    async def test_webdav_health_check_online(self, file_manager, mock_webdav_client):
        """测试WebDAV健康检查 - 在线"""
        mock_webdav_client.check_health.return_value = True

        with patch.object(file_manager, 'webdav_client', mock_webdav_client):
            is_healthy = await file_manager.check_webdav_health()

        assert is_healthy is True

    @pytest.mark.asyncio
    async def test_webdav_health_check_offline(self, file_manager, mock_webdav_client):
        """测试WebDAV健康检查 - 离线"""
        mock_webdav_client.check_health.return_value = False

        with patch.object(file_manager, 'webdav_client', mock_webdav_client):
            is_healthy = await file_manager.check_webdav_health()

        assert is_healthy is False

    @pytest.mark.asyncio
    async def test_webdav_status_update(self, file_manager, mock_webdav_client):
        """测试WebDAV状态更新"""
        # 初始状态：在线
        mock_webdav_client.check_health.return_value = True
        with patch.object(file_manager, 'webdav_client', mock_webdav_client):
            await file_manager.update_webdav_status()
            assert file_manager.webdav_available is True

        # 状态变更：离线
        mock_webdav_client.check_health.return_value = False
        with patch.object(file_manager, 'webdav_client', mock_webdav_client):
            await file_manager.update_webdav_status()
            assert file_manager.webdav_available is False


class TestFileManagerPerformance:
    """测试文件管理器性能"""

    @pytest.mark.asyncio
    async def test_cache_access_performance(self, file_manager, temp_cache_dir):
        """测试缓存访问性能（应<1秒）"""
        import time

        # 创建缓存文件
        cache_path = os.path.join(temp_cache_dir, "files")
        os.makedirs(cache_path, exist_ok=True)
        cached_file = os.path.join(cache_path, "test.jpg")
        with open(cached_file, 'wb') as f:
            f.write(b"x" * (1024 * 100))  # 100KB

        start_time = time.time()
        content = await file_manager.download_file("files/test.jpg")
        elapsed = time.time() - start_time

        assert content is not None
        assert elapsed < 1.0  # 应该<1秒
