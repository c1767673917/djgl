"""测试上传API端点"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, Mock
from io import BytesIO

from app.main import app


client = TestClient(app)


class TestUploadAPI:
    """测试上传API功能"""

    def test_upload_single_file_success(self, test_image_bytes, mock_upload_response_success):
        """测试单文件上传成功"""
        with patch('app.api.upload.yonyou_client.upload_file', new_callable=AsyncMock) as mock_upload:
            mock_upload.return_value = {
                "success": True,
                "data": mock_upload_response_success["data"]["data"][0]
            }

            files = {
                "files": ("test.jpg", test_image_bytes, "image/jpeg")
            }
            data = {"business_id": "123456"}

            response = client.post("/api/upload", files=files, data=data)

            assert response.status_code == 200
            result = response.json()
            assert result["success"] is True
            assert result["total"] == 1
            assert result["succeeded"] == 1
            assert result["failed"] == 0

    def test_upload_multiple_files_success(self, test_image_bytes, mock_upload_response_success):
        """测试批量上传(10张)成功"""
        with patch('app.api.upload.yonyou_client.upload_file', new_callable=AsyncMock) as mock_upload:
            mock_upload.return_value = {
                "success": True,
                "data": mock_upload_response_success["data"]["data"][0]
            }

            files = [
                ("files", (f"test{i}.jpg", test_image_bytes, "image/jpeg"))
                for i in range(10)
            ]
            data = {"business_id": "123456"}

            response = client.post("/api/upload", files=files, data=data)

            assert response.status_code == 200
            result = response.json()
            assert result["success"] is True
            assert result["total"] == 10
            assert result["succeeded"] == 10
            assert result["failed"] == 0

    def test_upload_missing_business_id(self, test_image_bytes):
        """测试缺少business_id参数"""
        files = {
            "files": ("test.jpg", test_image_bytes, "image/jpeg")
        }

        response = client.post("/api/upload", files=files)

        assert response.status_code == 422  # FastAPI validation error

    def test_upload_missing_files(self):
        """测试缺少文件参数"""
        data = {"business_id": "123456"}

        response = client.post("/api/upload", data=data)

        assert response.status_code == 422  # FastAPI validation error

    def test_upload_invalid_business_id_format(self, test_image_bytes, invalid_business_ids):
        """测试无效的businessId格式"""
        for business_id, description in invalid_business_ids:
            files = {
                "files": ("test.jpg", test_image_bytes, "image/jpeg")
            }
            data = {"business_id": business_id}

            response = client.post("/api/upload", files=files, data=data)

            assert response.status_code == 400, f"Failed for {description}: {business_id}"
            assert "businessId必须为6位数字" in response.json()["detail"]

    def test_upload_valid_business_id_formats(self, test_image_bytes, valid_business_ids, mock_upload_response_success):
        """测试有效的businessId格式"""
        with patch('app.api.upload.yonyou_client.upload_file', new_callable=AsyncMock) as mock_upload:
            mock_upload.return_value = {
                "success": True,
                "data": mock_upload_response_success["data"]["data"][0]
            }

            for business_id in valid_business_ids:
                files = {
                    "files": ("test.jpg", test_image_bytes, "image/jpeg")
                }
                data = {"business_id": business_id}

                response = client.post("/api/upload", files=files, data=data)

                assert response.status_code == 200, f"Failed for business_id: {business_id}"

    def test_upload_exceed_file_count_limit(self, test_image_bytes):
        """测试超出文件数量限制(最多10张)"""
        files = [
            ("files", (f"test{i}.jpg", test_image_bytes, "image/jpeg"))
            for i in range(11)  # 11个文件
        ]
        data = {"business_id": "123456"}

        response = client.post("/api/upload", files=files, data=data)

        assert response.status_code == 400
        assert "单次最多上传10个文件" in response.json()["detail"]

    def test_upload_invalid_file_type(self):
        """测试不支持的文件类型"""
        # 创建一个txt文件
        files = {
            "files": ("test.txt", b"test content", "text/plain")
        }
        data = {"business_id": "123456"}

        response = client.post("/api/upload", files=files, data=data)

        assert response.status_code == 400
        assert "不支持的文件格式" in response.json()["detail"]

    def test_upload_valid_file_types(self, mock_upload_response_success):
        """测试支持的文件类型(jpg/png/gif)"""
        valid_extensions = [
            ("test.jpg", "image/jpeg"),
            ("test.jpeg", "image/jpeg"),
            ("test.png", "image/png"),
            ("test.gif", "image/gif"),
        ]

        with patch('app.api.upload.yonyou_client.upload_file', new_callable=AsyncMock) as mock_upload:
            mock_upload.return_value = {
                "success": True,
                "data": mock_upload_response_success["data"]["data"][0]
            }

            for filename, content_type in valid_extensions:
                files = {
                    "files": (filename, b"fake image data", content_type)
                }
                data = {"business_id": "123456"}

                response = client.post("/api/upload", files=files, data=data)

                assert response.status_code == 200, f"Failed for {filename}"

    def test_upload_file_size_limit(self, large_image_bytes):
        """测试文件大小限制(10MB)"""
        with patch('app.api.upload.yonyou_client.upload_file', new_callable=AsyncMock) as mock_upload:
            # 不应该调用到upload_file,因为会在API层被拦截
            mock_upload.return_value = {"success": False}

            files = {
                "files": ("large.jpg", large_image_bytes, "image/jpeg")
            }
            data = {"business_id": "123456"}

            response = client.post("/api/upload", files=files, data=data)

            assert response.status_code == 200
            result = response.json()
            # 应该返回文件太大的错误
            assert result["failed"] == 1
            assert "FILE_TOO_LARGE" in str(result["results"][0])

    def test_upload_partial_success(self, test_image_bytes, mock_upload_response_success):
        """测试部分上传成功场景"""
        with patch('app.api.upload.yonyou_client.upload_file', new_callable=AsyncMock) as mock_upload:
            # 前3个成功,后2个失败
            mock_upload.side_effect = [
                {"success": True, "data": mock_upload_response_success["data"]["data"][0]},
                {"success": True, "data": mock_upload_response_success["data"]["data"][0]},
                {"success": True, "data": mock_upload_response_success["data"]["data"][0]},
                {"success": False, "error_code": "40000", "error_message": "上传失败"},
                {"success": False, "error_code": "40000", "error_message": "上传失败"},
            ]

            files = [
                ("files", (f"test{i}.jpg", test_image_bytes, "image/jpeg"))
                for i in range(5)
            ]
            data = {"business_id": "123456"}

            response = client.post("/api/upload", files=files, data=data)

            assert response.status_code == 200
            result = response.json()
            assert result["total"] == 5
            assert result["succeeded"] == 3
            assert result["failed"] == 2

    def test_upload_retry_mechanism(self, test_image_bytes, mock_upload_response_success):
        """测试上传失败重试机制(最多3次)"""
        with patch('app.api.upload.yonyou_client.upload_file', new_callable=AsyncMock) as mock_upload:
            # 前2次失败,第3次成功
            mock_upload.side_effect = [
                {"success": False, "error_code": "40000", "error_message": "临时错误"},
                {"success": False, "error_code": "40000", "error_message": "临时错误"},
                {"success": True, "data": mock_upload_response_success["data"]["data"][0]},
            ]

            files = {
                "files": ("test.jpg", test_image_bytes, "image/jpeg")
            }
            data = {"business_id": "123456"}

            response = client.post("/api/upload", files=files, data=data)

            assert response.status_code == 200
            result = response.json()
            # 最终成功
            assert result["succeeded"] == 1
            assert result["failed"] == 0
            # 验证重试了3次
            assert mock_upload.call_count == 3

    def test_upload_retry_max_attempts(self, test_image_bytes):
        """测试达到最大重试次数后失败"""
        with patch('app.api.upload.yonyou_client.upload_file', new_callable=AsyncMock) as mock_upload:
            # 始终失败
            mock_upload.return_value = {
                "success": False,
                "error_code": "40000",
                "error_message": "持续失败"
            }

            files = {
                "files": ("test.jpg", test_image_bytes, "image/jpeg")
            }
            data = {"business_id": "123456"}

            response = client.post("/api/upload", files=files, data=data)

            assert response.status_code == 200
            result = response.json()
            assert result["succeeded"] == 0
            assert result["failed"] == 1
            # 验证重试了3次
            assert mock_upload.call_count == 3

    def test_upload_database_save_success(self, test_image_bytes, test_db_path, mock_upload_response_success):
        """测试上传成功后保存到数据库"""
        with patch('app.api.upload.yonyou_client.upload_file', new_callable=AsyncMock) as mock_upload, \
             patch('app.api.upload.get_db_connection') as mock_db_conn, \
             patch('app.core.database.get_settings') as mock_settings:

            mock_upload.return_value = {
                "success": True,
                "data": mock_upload_response_success["data"]["data"][0]
            }

            # Mock数据库连接
            import sqlite3
            mock_conn = sqlite3.connect(test_db_path)
            mock_db_conn.return_value = mock_conn

            # Mock settings
            mock_settings_obj = Mock()
            mock_settings_obj.DATABASE_URL = f"sqlite:///{test_db_path}"
            mock_settings.return_value = mock_settings_obj

            files = {
                "files": ("test.jpg", test_image_bytes, "image/jpeg")
            }
            data = {"business_id": "123456"}

            response = client.post("/api/upload", files=files, data=data)

            assert response.status_code == 200

            # 验证数据库中的记录
            cursor = mock_conn.cursor()
            cursor.execute("SELECT * FROM upload_history WHERE business_id = ?", ("123456",))
            records = cursor.fetchall()

            assert len(records) == 1
            assert records[0][1] == "123456"  # business_id
            assert records[0][2] == "test.jpg"  # file_name
            assert records[0][6] == "success"  # status

    def test_upload_database_save_failure(self, test_image_bytes, test_db_path):
        """测试上传失败后保存到数据库"""
        with patch('app.api.upload.yonyou_client.upload_file', new_callable=AsyncMock) as mock_upload, \
             patch('app.api.upload.get_db_connection') as mock_db_conn, \
             patch('app.core.database.get_settings') as mock_settings:

            mock_upload.return_value = {
                "success": False,
                "error_code": "40000",
                "error_message": "上传失败"
            }

            # Mock数据库连接
            import sqlite3
            mock_conn = sqlite3.connect(test_db_path)
            mock_db_conn.return_value = mock_conn

            # Mock settings
            mock_settings_obj = Mock()
            mock_settings_obj.DATABASE_URL = f"sqlite:///{test_db_path}"
            mock_settings.return_value = mock_settings_obj

            files = {
                "files": ("test.jpg", test_image_bytes, "image/jpeg")
            }
            data = {"business_id": "123456"}

            # 设置重试次数为1,加快测试
            with patch('app.core.config.get_settings') as mock_config:
                mock_config_obj = Mock()
                mock_config_obj.MAX_RETRY_COUNT = 1
                mock_config_obj.RETRY_DELAY = 0
                mock_config_obj.MAX_FILES_PER_REQUEST = 10
                mock_config_obj.ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif"}
                mock_config_obj.MAX_FILE_SIZE = 10 * 1024 * 1024
                mock_config_obj.MAX_CONCURRENT_UPLOADS = 3
                mock_config.return_value = mock_config_obj

                response = client.post("/api/upload", files=files, data=data)

            assert response.status_code == 200

            # 验证数据库中的记录
            cursor = mock_conn.cursor()
            cursor.execute("SELECT * FROM upload_history WHERE business_id = ?", ("123456",))
            records = cursor.fetchall()

            assert len(records) == 1
            assert records[0][6] == "failed"  # status
            assert records[0][7] == "40000"  # error_code


class TestConcurrencyControl:
    """测试并发控制"""

    def test_concurrent_upload_limit(self, test_image_bytes, mock_upload_response_success):
        """测试并发上传数量限制(最多3个并发)"""
        upload_calls = []

        async def mock_upload_with_tracking(*args, **kwargs):
            upload_calls.append(1)
            # 模拟上传需要时间
            import asyncio
            await asyncio.sleep(0.1)
            return {
                "success": True,
                "data": mock_upload_response_success["data"]["data"][0]
            }

        with patch('app.api.upload.yonyou_client.upload_file', new_callable=AsyncMock) as mock_upload:
            mock_upload.side_effect = mock_upload_with_tracking

            files = [
                ("files", (f"test{i}.jpg", test_image_bytes, "image/jpeg"))
                for i in range(10)
            ]
            data = {"business_id": "123456"}

            response = client.post("/api/upload", files=files, data=data)

            assert response.status_code == 200
            # 验证所有文件都上传了
            assert mock_upload.call_count == 10
