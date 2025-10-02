"""集成测试 - 端到端测试完整流程"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, Mock
import sqlite3
import time

from app.main import app


client = TestClient(app)


class TestEndToEndUpload:
    """端到端上传流程测试"""

    @pytest.mark.asyncio
    async def test_complete_upload_workflow(
        self,
        test_image_bytes,
        test_db_path,
        mock_token_response_success,
        mock_upload_response_success
    ):
        """测试完整的上传工作流程"""
        with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get, \
             patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post, \
             patch('app.api.upload.get_db_connection') as mock_db_conn:

            # Mock Token获取
            mock_get_response = Mock()
            mock_get_response.json.return_value = mock_token_response_success
            mock_get.return_value = mock_get_response

            # Mock文件上传
            mock_post_response = Mock()
            mock_post_response.json.return_value = mock_upload_response_success
            mock_post.return_value = mock_post_response

            # Mock数据库
            mock_db_conn.return_value = sqlite3.connect(test_db_path)

            # 1. 上传文件
            files = {
                "files": ("test.jpg", test_image_bytes, "image/jpeg")
            }
            data = {"business_id": "123456"}

            upload_response = client.post("/api/upload", files=files, data=data)

            assert upload_response.status_code == 200
            upload_result = upload_response.json()
            assert upload_result["success"] is True
            assert upload_result["succeeded"] == 1

            # 2. 查询历史记录
            with patch('app.api.history.get_db_connection') as mock_history_db:
                mock_history_db.return_value = sqlite3.connect(test_db_path)

                history_response = client.get("/api/history/123456")

                assert history_response.status_code == 200
                history_result = history_response.json()
                assert history_result["total_count"] == 1
                assert history_result["success_count"] == 1
                assert history_result["records"][0]["file_name"] == "test.jpg"

    def test_batch_upload_workflow(
        self,
        test_image_bytes,
        test_db_path,
        mock_token_response_success,
        mock_upload_response_success
    ):
        """测试批量上传工作流程"""
        with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get, \
             patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post, \
             patch('app.api.upload.get_db_connection') as mock_db_conn:

            mock_get_response = Mock()
            mock_get_response.json.return_value = mock_token_response_success
            mock_get.return_value = mock_get_response

            mock_post_response = Mock()
            mock_post_response.json.return_value = mock_upload_response_success
            mock_post.return_value = mock_post_response

            mock_db_conn.return_value = sqlite3.connect(test_db_path)

            # 上传10个文件
            files = [
                ("files", (f"test{i}.jpg", test_image_bytes, "image/jpeg"))
                for i in range(10)
            ]
            data = {"business_id": "123456"}

            upload_response = client.post("/api/upload", files=files, data=data)

            assert upload_response.status_code == 200
            upload_result = upload_response.json()
            assert upload_result["total"] == 10
            assert upload_result["succeeded"] == 10

            # 验证所有文件都调用了上传API
            assert mock_post.call_count == 10

    def test_upload_with_retry_workflow(
        self,
        test_image_bytes,
        test_db_path,
        mock_token_response_success,
        mock_upload_response_success
    ):
        """测试包含重试的上传流程"""
        with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get, \
             patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post, \
             patch('app.api.upload.get_db_connection') as mock_db_conn, \
             patch('app.core.config.get_settings') as mock_settings:

            mock_get_response = Mock()
            mock_get_response.json.return_value = mock_token_response_success
            mock_get.return_value = mock_get_response

            # 前2次失败,第3次成功
            mock_post.side_effect = [
                Mock(json=Mock(return_value={"code": "40000", "message": "临时错误"})),
                Mock(json=Mock(return_value={"code": "40000", "message": "临时错误"})),
                Mock(json=Mock(return_value=mock_upload_response_success)),
            ]

            mock_db_conn.return_value = sqlite3.connect(test_db_path)

            # Mock settings
            mock_settings_obj = Mock()
            mock_settings_obj.MAX_RETRY_COUNT = 3
            mock_settings_obj.RETRY_DELAY = 0  # 加快测试
            mock_settings_obj.MAX_FILES_PER_REQUEST = 10
            mock_settings_obj.ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif"}
            mock_settings_obj.MAX_FILE_SIZE = 10 * 1024 * 1024
            mock_settings_obj.MAX_CONCURRENT_UPLOADS = 3
            mock_settings.return_value = mock_settings_obj

            files = {
                "files": ("test.jpg", test_image_bytes, "image/jpeg")
            }
            data = {"business_id": "123456"}

            upload_response = client.post("/api/upload", files=files, data=data)

            assert upload_response.status_code == 200
            # 最终成功
            assert upload_response.json()["succeeded"] == 1
            # 验证重试了3次
            assert mock_post.call_count == 3


class TestTokenExpiredScenario:
    """测试Token过期场景"""

    def test_token_expired_and_refresh(
        self,
        test_image_bytes,
        mock_token_response_success,
        mock_upload_response_token_expired_string,
        mock_upload_response_success
    ):
        """测试Token过期后自动刷新并重试"""
        with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get, \
             patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post:

            mock_get_response = Mock()
            mock_get_response.json.return_value = mock_token_response_success
            mock_get.return_value = mock_get_response

            # 第一次上传Token过期,第二次成功
            mock_post.side_effect = [
                Mock(json=Mock(return_value=mock_upload_response_token_expired_string)),
                Mock(json=Mock(return_value=mock_upload_response_success)),
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
            # 验证调用了2次Token获取(第二次是force_refresh)
            assert mock_get.call_count == 2


class TestErrorHandling:
    """测试错误处理"""

    def test_partial_upload_failure(
        self,
        test_image_bytes,
        test_db_path,
        mock_token_response_success,
        mock_upload_response_success
    ):
        """测试部分文件上传失败的处理"""
        with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get, \
             patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post, \
             patch('app.api.upload.get_db_connection') as mock_db_conn, \
             patch('app.core.config.get_settings') as mock_settings:

            mock_get_response = Mock()
            mock_get_response.json.return_value = mock_token_response_success
            mock_get.return_value = mock_get_response

            # 3个成功,2个失败
            mock_post.side_effect = [
                Mock(json=Mock(return_value=mock_upload_response_success)),
                Mock(json=Mock(return_value=mock_upload_response_success)),
                Mock(json=Mock(return_value=mock_upload_response_success)),
                Mock(json=Mock(return_value={"code": "40000", "message": "上传失败"})),
                Mock(json=Mock(return_value={"code": "40000", "message": "上传失败"})),
            ]

            mock_db_conn.return_value = sqlite3.connect(test_db_path)

            # Mock settings
            mock_settings_obj = Mock()
            mock_settings_obj.MAX_RETRY_COUNT = 1
            mock_settings_obj.RETRY_DELAY = 0
            mock_settings_obj.MAX_FILES_PER_REQUEST = 10
            mock_settings_obj.ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif"}
            mock_settings_obj.MAX_FILE_SIZE = 10 * 1024 * 1024
            mock_settings_obj.MAX_CONCURRENT_UPLOADS = 3
            mock_settings.return_value = mock_settings_obj

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

    def test_network_error_handling(
        self,
        test_image_bytes,
        mock_token_response_success
    ):
        """测试网络错误处理"""
        with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get, \
             patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post:

            mock_get_response = Mock()
            mock_get_response.json.return_value = mock_token_response_success
            mock_get.return_value = mock_get_response

            # 模拟网络超时
            mock_post.side_effect = Exception("Connection timeout")

            files = {
                "files": ("test.jpg", test_image_bytes, "image/jpeg")
            }
            data = {"business_id": "123456"}

            response = client.post("/api/upload", files=files, data=data)

            assert response.status_code == 200
            result = response.json()
            assert result["failed"] == 1
            assert "NETWORK_ERROR" in str(result["results"][0])


class TestDatabasePersistence:
    """测试数据持久化"""

    def test_upload_history_persistence(
        self,
        test_image_bytes,
        test_db_path,
        mock_token_response_success,
        mock_upload_response_success
    ):
        """测试上传历史正确保存到数据库"""
        with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get, \
             patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post, \
             patch('app.api.upload.get_db_connection') as mock_upload_db, \
             patch('app.api.history.get_db_connection') as mock_history_db:

            mock_get_response = Mock()
            mock_get_response.json.return_value = mock_token_response_success
            mock_get.return_value = mock_get_response

            mock_post_response = Mock()
            mock_post_response.json.return_value = mock_upload_response_success
            mock_post.return_value = mock_post_response

            mock_upload_db.return_value = sqlite3.connect(test_db_path)
            mock_history_db.return_value = sqlite3.connect(test_db_path)

            # 上传文件
            files = {
                "files": ("test.jpg", test_image_bytes, "image/jpeg")
            }
            data = {"business_id": "123456"}

            client.post("/api/upload", files=files, data=data)

            # 验证数据库记录
            conn = sqlite3.connect(test_db_path)
            cursor = conn.cursor()

            cursor.execute("SELECT * FROM upload_history WHERE business_id = ?", ("123456",))
            record = cursor.fetchone()

            assert record is not None
            assert record[2] == "test.jpg"  # file_name
            assert record[6] == "success"  # status
            assert record[9] == "file_id_12345"  # yonyou_file_id

            conn.close()

    def test_multiple_business_ids_isolation(
        self,
        test_image_bytes,
        test_db_path,
        mock_token_response_success,
        mock_upload_response_success
    ):
        """测试不同业务单据的数据隔离"""
        with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get, \
             patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post, \
             patch('app.api.upload.get_db_connection') as mock_upload_db, \
             patch('app.api.history.get_db_connection') as mock_history_db:

            mock_get_response = Mock()
            mock_get_response.json.return_value = mock_token_response_success
            mock_get.return_value = mock_get_response

            mock_post_response = Mock()
            mock_post_response.json.return_value = mock_upload_response_success
            mock_post.return_value = mock_post_response

            mock_upload_db.return_value = sqlite3.connect(test_db_path)
            mock_history_db.return_value = sqlite3.connect(test_db_path)

            # 上传到不同的业务单据
            for business_id in ["123456", "654321"]:
                files = {
                    "files": (f"test_{business_id}.jpg", test_image_bytes, "image/jpeg")
                }
                data = {"business_id": business_id}

                client.post("/api/upload", files=files, data=data)

            # 验证查询隔离
            response1 = client.get("/api/history/123456")
            result1 = response1.json()
            assert result1["total_count"] == 1

            response2 = client.get("/api/history/654321")
            result2 = response2.json()
            assert result2["total_count"] == 1


class TestPerformance:
    """测试性能相关场景"""

    def test_concurrent_upload_performance(
        self,
        test_image_bytes,
        mock_token_response_success,
        mock_upload_response_success
    ):
        """测试并发上传的性能"""
        with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get, \
             patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post:

            mock_get_response = Mock()
            mock_get_response.json.return_value = mock_token_response_success
            mock_get.return_value = mock_get_response

            # 模拟每次上传需要0.1秒
            async def slow_upload(*args, **kwargs):
                import asyncio
                await asyncio.sleep(0.1)
                mock_response = Mock()
                mock_response.json.return_value = mock_upload_response_success
                return mock_response

            mock_post.side_effect = slow_upload

            files = [
                ("files", (f"test{i}.jpg", test_image_bytes, "image/jpeg"))
                for i in range(10)
            ]
            data = {"business_id": "123456"}

            start_time = time.time()
            response = client.post("/api/upload", files=files, data=data)
            elapsed_time = time.time() - start_time

            assert response.status_code == 200

            # 并发3个,10个文件应该需要大约 (10/3) * 0.1 = 0.33秒
            # 如果是串行,需要 10 * 0.1 = 1秒
            # 验证并发确实生效(允许一定误差)
            assert elapsed_time < 0.8, f"上传耗时过长: {elapsed_time}秒,可能并发控制未生效"
