"""备份服务功能测试"""
import pytest
import os
import tempfile
import tarfile
from datetime import timedelta
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from app.core.backup_service import BackupService
from app.core.exceptions import BackupError
from app.core.timezone import get_beijing_now


@pytest.fixture
def temp_backup_dir():
    """创建临时备份目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def temp_db_file():
    """创建临时数据库文件"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.db', delete=False) as f:
        db_path = f.name
        f.write("mock database content")
    yield db_path
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture
def temp_env_file():
    """创建临时.env文件"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
        env_path = f.name
        f.write("MOCK_VAR=value\n")
    yield env_path
    if os.path.exists(env_path):
        os.unlink(env_path)


@pytest.fixture
def backup_service(temp_backup_dir, temp_db_file, temp_env_file):
    """创建备份服务实例"""
    return BackupService(
        db_path=temp_db_file,
        env_path=temp_env_file,
        backup_dir=temp_backup_dir,
        retention_days=30
    )


@pytest.fixture
def mock_webdav_client():
    """Mock WebDAV客户端"""
    mock_client = AsyncMock()
    mock_client.upload_file.return_value = "backup_etag"
    mock_client.list_files.return_value = []
    mock_client.delete_file.return_value = True
    return mock_client


class TestBackupServiceInitialization:
    """测试备份服务初始化"""

    def test_init_with_valid_params(self, temp_backup_dir, temp_db_file, temp_env_file):
        """测试使用有效参数初始化"""
        service = BackupService(
            db_path=temp_db_file,
            env_path=temp_env_file,
            backup_dir=temp_backup_dir,
            retention_days=30
        )
        assert service.db_path == temp_db_file
        assert service.env_path == temp_env_file
        assert service.backup_dir == temp_backup_dir
        assert service.retention_days == 30

    def test_backup_directory_creation(self, temp_db_file, temp_env_file):
        """测试备份目录自动创建"""
        backup_path = os.path.join(tempfile.gettempdir(), "test_backups")
        service = BackupService(
            db_path=temp_db_file,
            env_path=temp_env_file,
            backup_dir=backup_path
        )
        assert os.path.exists(backup_path)
        # 清理
        if os.path.exists(backup_path):
            os.rmdir(backup_path)


class TestBackupServiceCreateBackup:
    """测试备份服务创建备份"""

    @pytest.mark.asyncio
    async def test_create_backup_success(self, backup_service, temp_backup_dir):
        """测试成功创建备份"""
        result = await backup_service.create_backup()

        assert result["success"] is True
        assert "backup_file" in result
        assert result["backup_file"].startswith("backup_")
        assert result["backup_file"].endswith(".tar.gz")

        # 验证备份文件存在
        backup_path = os.path.join(temp_backup_dir, result["backup_file"])
        assert os.path.exists(backup_path)

        # 验证备份文件内容
        with tarfile.open(backup_path, 'r:gz') as tar:
            members = tar.getmembers()
            assert len(members) >= 2  # 至少包含数据库和.env文件

    @pytest.mark.asyncio
    async def test_backup_filename_format(self, backup_service):
        """测试备份文件名格式"""
        result = await backup_service.create_backup()

        backup_filename = result["backup_file"]
        # 格式应该是：backup_YYYYMMDD_HHMMSS.tar.gz
        assert backup_filename.startswith("backup_")
        assert backup_filename.endswith(".tar.gz")
        assert len(backup_filename) == len("backup_20251027_120000.tar.gz")

    @pytest.mark.asyncio
    async def test_backup_file_integrity(self, backup_service, temp_backup_dir, temp_db_file, temp_env_file):
        """测试备份文件完整性"""
        result = await backup_service.create_backup()

        backup_path = os.path.join(temp_backup_dir, result["backup_file"])

        # 验证tar.gz文件可以正常打开
        with tarfile.open(backup_path, 'r:gz') as tar:
            # 提取所有文件
            extract_dir = os.path.join(temp_backup_dir, "extracted")
            os.makedirs(extract_dir, exist_ok=True)
            tar.extractall(extract_dir)

            # 验证数据库文件存在
            db_name = os.path.basename(temp_db_file)
            extracted_db = os.path.join(extract_dir, db_name)
            assert os.path.exists(extracted_db)

            # 验证.env文件存在
            env_name = os.path.basename(temp_env_file)
            extracted_env = os.path.join(extract_dir, env_name)
            assert os.path.exists(extracted_env)


class TestBackupServiceUploadToWebDAV:
    """测试备份服务上传到WebDAV"""

    @pytest.mark.asyncio
    async def test_upload_backup_to_webdav_success(self, backup_service, mock_webdav_client, temp_backup_dir):
        """测试成功上传备份到WebDAV"""
        # 先创建备份
        backup_result = await backup_service.create_backup()
        backup_file = backup_result["backup_file"]

        with patch.object(backup_service, 'webdav_client', mock_webdav_client):
            upload_result = await backup_service.upload_to_webdav(backup_file)

        assert upload_result["success"] is True
        mock_webdav_client.upload_file.assert_called_once()

    @pytest.mark.asyncio
    async def test_upload_nonexistent_backup(self, backup_service, mock_webdav_client):
        """测试上传不存在的备份文件"""
        with patch.object(backup_service, 'webdav_client', mock_webdav_client):
            with pytest.raises(BackupError):
                await backup_service.upload_to_webdav("nonexistent_backup.tar.gz")


class TestBackupServiceCleanup:
    """测试备份服务清理功能"""

    @pytest.mark.asyncio
    async def test_cleanup_old_backups_local(self, backup_service, temp_backup_dir):
        """测试清理本地过期备份"""
        # 创建测试备份文件
        # 有效备份（10天前）
        valid_backup = os.path.join(temp_backup_dir, "backup_20251017_120000.tar.gz")
        with open(valid_backup, 'w') as f:
            f.write("valid backup")
        base_now = get_beijing_now()
        valid_time = (base_now - timedelta(days=10)).timestamp()
        os.utime(valid_backup, (valid_time, valid_time))

        # 过期备份（35天前）
        expired_backup = os.path.join(temp_backup_dir, "backup_20250922_120000.tar.gz")
        with open(expired_backup, 'w') as f:
            f.write("expired backup")
        expired_time = (base_now - timedelta(days=35)).timestamp()
        os.utime(expired_backup, (expired_time, expired_time))

        # 执行清理
        result = await backup_service.cleanup_old_backups_local()

        # 验证过期备份被删除，有效备份保留
        assert not os.path.exists(expired_backup)
        assert os.path.exists(valid_backup)
        assert result["deleted_count"] > 0

    @pytest.mark.asyncio
    async def test_cleanup_old_backups_webdav(self, backup_service, mock_webdav_client):
        """测试清理WebDAV上的过期备份"""
        # Mock WebDAV上的备份文件列表
        current_time = get_beijing_now()
        mock_files = [
            {
                "href": "/dav/backups/backup_20251017_120000.tar.gz",  # 10天前，有效
                "modified": (current_time - timedelta(days=10)).isoformat()
            },
            {
                "href": "/dav/backups/backup_20250922_120000.tar.gz",  # 35天前，过期
                "modified": (current_time - timedelta(days=35)).isoformat()
            }
        ]
        mock_webdav_client.list_files.return_value = mock_files

        with patch.object(backup_service, 'webdav_client', mock_webdav_client):
            result = await backup_service.cleanup_old_backups_webdav()

        # 验证过期备份被删除
        assert result["deleted_count"] > 0
        # 验证delete_file被调用删除过期文件
        assert mock_webdav_client.delete_file.called

    @pytest.mark.asyncio
    async def test_retention_policy_30_days(self, backup_service, temp_backup_dir):
        """测试30天保留策略"""
        # 创建不同时间的备份文件
        test_cases = [
            (1, True),   # 1天前 - 保留
            (15, True),  # 15天前 - 保留
            (29, True),  # 29天前 - 保留
            (30, True),  # 30天前 - 保留
            (31, False), # 31天前 - 删除
            (60, False), # 60天前 - 删除
        ]

        reference_now = get_beijing_now()

        for days_ago, should_keep in test_cases:
            target_time = reference_now - timedelta(days=days_ago)
            filename = f"backup_{target_time.strftime('%Y%m%d_%H%M%S')}.tar.gz"
            filepath = os.path.join(temp_backup_dir, filename)
            with open(filepath, 'w') as f:
                f.write(f"backup {days_ago} days ago")
            file_time = target_time.timestamp()
            os.utime(filepath, (file_time, file_time))

        # 执行清理
        await backup_service.cleanup_old_backups_local()

        # 验证保留策略
        for days_ago, should_keep in test_cases:
            target_time = reference_now - timedelta(days=days_ago)
            filename = f"backup_{target_time.strftime('%Y%m%d_%H%M%S')}.tar.gz"
            filepath = os.path.join(temp_backup_dir, filename)
            if should_keep:
                assert os.path.exists(filepath), f"文件应该保留: {days_ago}天前"
            else:
                assert not os.path.exists(filepath), f"文件应该删除: {days_ago}天前"


class TestBackupServiceFullWorkflow:
    """测试备份服务完整工作流"""

    @pytest.mark.asyncio
    async def test_full_backup_workflow(self, backup_service, mock_webdav_client):
        """测试完整的备份工作流"""
        with patch.object(backup_service, 'webdav_client', mock_webdav_client):
            # 1. 创建备份
            backup_result = await backup_service.create_backup()
            assert backup_result["success"] is True

            # 2. 上传到WebDAV
            upload_result = await backup_service.upload_to_webdav(backup_result["backup_file"])
            assert upload_result["success"] is True

            # 3. 清理过期备份
            cleanup_result = await backup_service.cleanup_old_backups_local()
            assert "deleted_count" in cleanup_result


class TestBackupServiceErrorHandling:
    """测试备份服务错误处理"""

    @pytest.mark.asyncio
    async def test_create_backup_db_not_found(self, temp_backup_dir, temp_env_file):
        """测试数据库文件不存在时的错误处理"""
        service = BackupService(
            db_path="/nonexistent/database.db",
            env_path=temp_env_file,
            backup_dir=temp_backup_dir
        )

        with pytest.raises(BackupError):
            await service.create_backup()

    @pytest.mark.asyncio
    async def test_create_backup_env_not_found(self, temp_backup_dir, temp_db_file):
        """测试.env文件不存在时的错误处理"""
        service = BackupService(
            db_path=temp_db_file,
            env_path="/nonexistent/.env",
            backup_dir=temp_backup_dir
        )

        # .env文件不存在时应该只备份数据库，不应该抛出错误
        result = await service.create_backup()
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_upload_webdav_connection_error(self, backup_service, mock_webdav_client):
        """测试WebDAV连接错误"""
        from app.core.exceptions import WebDAVNetworkError

        backup_result = await backup_service.create_backup()
        mock_webdav_client.upload_file.side_effect = WebDAVNetworkError("Connection failed")

        with patch.object(backup_service, 'webdav_client', mock_webdav_client):
            with pytest.raises(BackupError):
                await backup_service.upload_to_webdav(backup_result["backup_file"])


class TestBackupServiceLogging:
    """测试备份服务日志记录"""

    @pytest.mark.asyncio
    async def test_backup_logging(self, backup_service, temp_backup_dir):
        """测试备份操作日志记录"""
        with patch('app.core.backup_service.logger') as mock_logger:
            await backup_service.create_backup()

            # 验证日志被记录
            assert mock_logger.info.called
            # 验证日志包含备份文件名
            calls = [str(call) for call in mock_logger.info.call_args_list]
            assert any("backup_" in str(call) for call in calls)
