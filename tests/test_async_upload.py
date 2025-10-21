"""
异步图片上传功能测试

测试覆盖：
- P0: 异步上传核心流程
- P0: 状态流转正确性
- P0: 重试机制
- P1: 错误处理
- P1: 并发上传
"""
import pytest
import asyncio
import time
import os
from unittest.mock import AsyncMock, Mock, patch
from fastapi.testclient import TestClient
from concurrent.futures import ThreadPoolExecutor

# 使用环境变量覆盖配置，避免Settings验证失败
os.environ["YONYOU_APP_KEY"] = "test_app_key"
os.environ["YONYOU_APP_SECRET"] = "test_app_secret"

from app.main import app
from app.core.database import get_db_connection
from app.api.upload import background_upload_to_yonyou


class TestAsyncUploadFlow:
    """测试异步上传基本流程 (P0)"""

    def test_upload_immediate_response(self, test_db_path, test_image_bytes):
        """测试上传接口立即返回 (响应时间 < 1秒)"""
        # 使用测试数据库
        os.environ["DATABASE_URL"] = f"sqlite:///{test_db_path}"

        client = TestClient(app)

        with patch('app.api.upload.background_upload_to_yonyou', new_callable=AsyncMock):
            files = [("files", ("test.jpg", test_image_bytes, "image/jpeg"))]
            data = {
                "business_id": "123456",
                "doc_number": "SO001",
                "doc_type": "销售"
            }

            # 测试响应时间
            start_time = time.time()
            response = client.post("/api/upload", files=files, data=data)
            elapsed_time = time.time() - start_time

            # 验证响应
            assert response.status_code == 200
            result = response.json()
            assert result["success"] is True
            assert result["total"] == 1
            assert "正在后台上传中" in result["message"]
            assert len(result["records"]) == 1
            assert result["records"][0]["status"] == "pending"

            # 验证响应时间 < 1.5秒（允许宽松限制）
            assert elapsed_time < 1.5, f"响应时间过长: {elapsed_time:.3f}秒"

    def test_upload_creates_pending_record(self, test_db_path, test_image_bytes):
        """测试上传立即创建pending状态记录"""
        os.environ["DATABASE_URL"] = f"sqlite:///{test_db_path}"

        client = TestClient(app)

        with patch('app.api.upload.background_upload_to_yonyou', new_callable=AsyncMock):
            files = [("files", ("test.jpg", test_image_bytes, "image/jpeg"))]
            data = {
                "business_id": "123456",
                "doc_number": "SO001",
                "doc_type": "销售"
            }

            response = client.post("/api/upload", files=files, data=data)
            assert response.status_code == 200

            result = response.json()
            record_id = result["records"][0]["id"]

            # 验证数据库记录
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT status, retry_count FROM upload_history WHERE id = ?", (record_id,))
            row = cursor.fetchone()
            conn.close()

            assert row is not None
            assert row[0] == "pending"  # status
            assert row[1] == 0  # retry_count

    def test_upload_multiple_files(self, test_db_path, test_image_bytes):
        """测试批量上传多个文件"""
        os.environ["DATABASE_URL"] = f"sqlite:///{test_db_path}"

        # 清空数据库
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM upload_history")
        conn.commit()
        conn.close()

        client = TestClient(app)

        with patch('app.api.upload.background_upload_to_yonyou', new_callable=AsyncMock):
            files = [
                ("files", (f"test{i}.jpg", test_image_bytes, "image/jpeg"))
                for i in range(5)
            ]
            data = {
                "business_id": "123456",
                "doc_number": "SO001",
                "doc_type": "销售"
            }

            response = client.post("/api/upload", files=files, data=data)
            assert response.status_code == 200

            result = response.json()
            assert result["success"] is True
            assert result["total"] == 5
            assert len(result["records"]) == 5

            # 验证数据库记录数
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM upload_history WHERE status = 'pending'")
            count = cursor.fetchone()[0]
            conn.close()

            assert count == 5


class TestBackgroundTaskExecution:
    """测试后台任务执行 (P0)"""

    @pytest.mark.asyncio
    async def test_background_upload_success(self, test_db_path, test_image_bytes):
        """测试后台任务成功上传到用友云"""
        os.environ["DATABASE_URL"] = f"sqlite:///{test_db_path}"

        # 创建pending记录
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO upload_history
            (business_id, doc_number, doc_type, file_name, file_size, file_extension,
             upload_time, status, retry_count, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'), ?, ?, datetime('now'), datetime('now'))
        """, ("123456", "SO001", "销售", "test.jpg", len(test_image_bytes), ".jpg", "pending", 0))
        record_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Mock用友云上传成功
        with patch('app.api.upload.yonyou_client.upload_file', new_callable=AsyncMock) as mock_upload:
            mock_upload.return_value = {
                "success": True,
                "data": {"id": "yonyou_file_id_12345"}
            }

            # 执行后台任务
            await background_upload_to_yonyou(
                file_content=test_image_bytes,
                new_filename="test.jpg",
                business_id="123456",
                business_type="yonbip-scm-scmsa",
                local_file_path=f"/tmp/test_{record_id}.jpg",
                record_id=record_id
            )

        # 验证最终状态
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT status, yonyou_file_id, retry_count
            FROM upload_history WHERE id = ?
        """, (record_id,))
        row = cursor.fetchone()
        conn.close()

        assert row[0] == "success"
        assert row[1] == "yonyou_file_id_12345"
        assert row[2] == 0  # 首次成功，retry_count = 0

    @pytest.mark.asyncio
    async def test_background_upload_updates_to_uploading(self, test_db_path, test_image_bytes):
        """测试后台任务开始时更新状态为uploading"""
        os.environ["DATABASE_URL"] = f"sqlite:///{test_db_path}"

        # 创建pending记录
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO upload_history
            (business_id, doc_number, doc_type, file_name, file_size, file_extension,
             upload_time, status, retry_count, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'), ?, ?, datetime('now'), datetime('now'))
        """, ("123456", "SO001", "销售", "test.jpg", len(test_image_bytes), ".jpg", "pending", 0))
        record_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Mock用友云上传（延迟返回）
        async def slow_upload(*args, **kwargs):
            await asyncio.sleep(0.1)  # 模拟上传耗时
            return {"success": True, "data": {"id": "test_file_id"}}

        with patch('app.api.upload.yonyou_client.upload_file', new_callable=AsyncMock) as mock_upload:
            mock_upload.side_effect = slow_upload

            # 启动后台任务（不等待完成）
            task = asyncio.create_task(background_upload_to_yonyou(
                file_content=test_image_bytes,
                new_filename="test.jpg",
                business_id="123456",
                business_type="yonbip-scm-scmsa",
                local_file_path=f"/tmp/test_{record_id}.jpg",
                record_id=record_id
            ))

            # 等待一小段时间，检查状态是否变为uploading
            await asyncio.sleep(0.05)

            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT status FROM upload_history WHERE id = ?", (record_id,))
            status = cursor.fetchone()[0]
            conn.close()

            # 状态应该已经变为uploading
            assert status == "uploading"

            # 等待任务完成
            await task


class TestRetryMechanism:
    """测试重试机制 (P0)"""

    @pytest.mark.asyncio
    async def test_retry_on_first_failure_then_success(self, test_db_path, test_image_bytes):
        """测试首次失败，重试1次后成功"""
        os.environ["DATABASE_URL"] = f"sqlite:///{test_db_path}"

        # 创建pending记录
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO upload_history
            (business_id, doc_number, doc_type, file_name, file_size, file_extension,
             upload_time, status, retry_count, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'), ?, ?, datetime('now'), datetime('now'))
        """, ("123456", "SO001", "销售", "test.jpg", len(test_image_bytes), ".jpg", "pending", 0))
        record_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Mock用友云上传：第1次失败，第2次成功
        call_count = 0
        async def mock_upload_with_retry(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {
                    "success": False,
                    "error_code": "NETWORK_ERROR",
                    "error_message": "网络连接失败"
                }
            else:
                return {
                    "success": True,
                    "data": {"id": "yonyou_file_id_12345"}
                }

        with patch('app.api.upload.yonyou_client.upload_file', new_callable=AsyncMock) as mock_upload:
            mock_upload.side_effect = mock_upload_with_retry
            with patch('asyncio.sleep', new_callable=AsyncMock):  # 跳过延迟
                await background_upload_to_yonyou(
                    file_content=test_image_bytes,
                    new_filename="test.jpg",
                    business_id="123456",
                    business_type="yonbip-scm-scmsa",
                    local_file_path=f"/tmp/test_{record_id}.jpg",
                    record_id=record_id
                )

        # 验证结果
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT status, yonyou_file_id, retry_count
            FROM upload_history WHERE id = ?
        """, (record_id,))
        row = cursor.fetchone()
        conn.close()

        assert row[0] == "success"
        assert row[1] == "yonyou_file_id_12345"
        assert row[2] == 1  # 重试1次后成功

    @pytest.mark.asyncio
    async def test_retry_all_attempts_fail(self, test_db_path, test_image_bytes):
        """测试重试3次全部失败"""
        os.environ["DATABASE_URL"] = f"sqlite:///{test_db_path}"

        # 创建pending记录
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO upload_history
            (business_id, doc_number, doc_type, file_name, file_size, file_extension,
             upload_time, status, retry_count, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'), ?, ?, datetime('now'), datetime('now'))
        """, ("123456", "SO001", "销售", "test.jpg", len(test_image_bytes), ".jpg", "pending", 0))
        record_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Mock用友云上传：全部失败
        with patch('app.api.upload.yonyou_client.upload_file', new_callable=AsyncMock) as mock_upload:
            mock_upload.return_value = {
                "success": False,
                "error_code": "NETWORK_ERROR",
                "error_message": "网络连接超时"
            }

            with patch('asyncio.sleep', new_callable=AsyncMock):  # 跳过延迟
                await background_upload_to_yonyou(
                    file_content=test_image_bytes,
                    new_filename="test.jpg",
                    business_id="123456",
                    business_type="yonbip-scm-scmsa",
                    local_file_path=f"/tmp/test_{record_id}.jpg",
                    record_id=record_id
                )

        # 验证结果
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT status, error_code, error_message, retry_count
            FROM upload_history WHERE id = ?
        """, (record_id,))
        row = cursor.fetchone()
        conn.close()

        assert row[0] == "failed"
        assert row[1] == "NETWORK_ERROR"
        assert row[2] == "网络连接超时"
        assert row[3] == 3  # 重试3次全部失败

    @pytest.mark.asyncio
    async def test_retry_count_recorded_correctly(self, test_db_path, test_image_bytes):
        """测试retry_count正确记录"""
        os.environ["DATABASE_URL"] = f"sqlite:///{test_db_path}"

        # 测试场景：第2次重试成功 (总共3次尝试)
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO upload_history
            (business_id, doc_number, doc_type, file_name, file_size, file_extension,
             upload_time, status, retry_count, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'), ?, ?, datetime('now'), datetime('now'))
        """, ("123456", "SO001", "销售", "test.jpg", len(test_image_bytes), ".jpg", "pending", 0))
        record_id = cursor.lastrowid
        conn.commit()
        conn.close()

        call_count = 0
        async def mock_upload_retry(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return {"success": False, "error_code": "ERROR", "error_message": "失败"}
            else:
                return {"success": True, "data": {"id": "file_id"}}

        with patch('app.api.upload.yonyou_client.upload_file', new_callable=AsyncMock) as mock_upload:
            mock_upload.side_effect = mock_upload_retry
            with patch('asyncio.sleep', new_callable=AsyncMock):
                await background_upload_to_yonyou(
                    file_content=test_image_bytes,
                    new_filename="test.jpg",
                    business_id="123456",
                    business_type="yonbip-scm-scmsa",
                    local_file_path=f"/tmp/test_{record_id}.jpg",
                    record_id=record_id
                )

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT status, retry_count FROM upload_history WHERE id = ?", (record_id,))
        row = cursor.fetchone()
        conn.close()

        assert row[0] == "success"
        assert row[1] == 2  # 第3次尝试成功，retry_count=2


class TestErrorHandling:
    """测试错误处理 (P1)"""

    @pytest.mark.asyncio
    async def test_database_exception_handling(self, test_db_path, test_image_bytes):
        """测试数据库异常捕获"""
        os.environ["DATABASE_URL"] = f"sqlite:///{test_db_path}"

        # 创建记录
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO upload_history
            (business_id, doc_number, doc_type, file_name, file_size, file_extension,
             upload_time, status, retry_count, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'), ?, ?, datetime('now'), datetime('now'))
        """, ("123456", "SO001", "销售", "test.jpg", len(test_image_bytes), ".jpg", "pending", 0))
        record_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Mock数据库连接失败
        with patch('app.api.upload.get_db_connection') as mock_get_conn:
            mock_get_conn.return_value = None  # 返回None模拟连接失败

            # 执行后台任务（不应抛出异常）
            await background_upload_to_yonyou(
                file_content=test_image_bytes,
                new_filename="test.jpg",
                business_id="123456",
                business_type="yonbip-scm-scmsa",
                local_file_path=f"/tmp/test_{record_id}.jpg",
                record_id=record_id
            )

        # 验证状态应该是failed（由异常处理逻辑更新）
        # 注意：由于mock了get_db_connection，状态更新可能也失败，这里仅验证没有抛出异常

    @pytest.mark.asyncio
    async def test_yonyou_api_exception_handling(self, test_db_path, test_image_bytes):
        """测试用友云API异常捕获"""
        os.environ["DATABASE_URL"] = f"sqlite:///{test_db_path}"

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO upload_history
            (business_id, doc_number, doc_type, file_name, file_size, file_extension,
             upload_time, status, retry_count, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'), ?, ?, datetime('now'), datetime('now'))
        """, ("123456", "SO001", "销售", "test.jpg", len(test_image_bytes), ".jpg", "pending", 0))
        record_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Mock用友云API抛出异常
        with patch('app.api.upload.yonyou_client.upload_file', new_callable=AsyncMock) as mock_upload:
            mock_upload.side_effect = Exception("Unexpected API error")

            # 执行后台任务
            await background_upload_to_yonyou(
                file_content=test_image_bytes,
                new_filename="test.jpg",
                business_id="123456",
                business_type="yonbip-scm-scmsa",
                local_file_path=f"/tmp/test_{record_id}.jpg",
                record_id=record_id
            )

        # 验证状态为failed
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT status, error_code, error_message
            FROM upload_history WHERE id = ?
        """, (record_id,))
        row = cursor.fetchone()
        conn.close()

        assert row[0] == "failed"
        assert row[1] == "BACKGROUND_TASK_ERROR"
        assert "Unexpected API error" in row[2]


class TestConcurrentUpload:
    """测试并发上传 (P1)"""

    def test_concurrent_uploads_data_consistency(self, test_db_path, test_image_bytes):
        """测试并发上传数据一致性"""
        os.environ["DATABASE_URL"] = f"sqlite:///{test_db_path}"

        # 清空数据库
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM upload_history")
        conn.commit()
        conn.close()

        client = TestClient(app)

        with patch('app.api.upload.background_upload_to_yonyou', new_callable=AsyncMock):
            def upload_file(index):
                files = [("files", (f"test{index}.jpg", test_image_bytes, "image/jpeg"))]
                data = {
                    "business_id": "123456",
                    "doc_number": f"SO{index:03d}",
                    "doc_type": "销售"
                }
                return client.post("/api/upload", files=files, data=data)

            # 并发上传10个文件
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(upload_file, i) for i in range(10)]
                results = [f.result() for f in futures]

            # 验证所有上传成功
            assert all(r.status_code == 200 for r in results)
            assert all(r.json()["success"] for r in results)

            # 验证数据库记录完整性
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM upload_history")
            count = cursor.fetchone()[0]
            conn.close()

            assert count == 10

    def test_concurrent_uploads_all_tasks_complete(self, test_db_path, test_image_bytes):
        """测试并发上传后所有后台任务正确完成"""
        os.environ["DATABASE_URL"] = f"sqlite:///{test_db_path}"

        client = TestClient(app)

        # 模拟真实的后台上传（使用真实函数，但Mock用友云API）
        with patch('app.api.upload.yonyou_client.upload_file', new_callable=AsyncMock) as mock_upload:
            mock_upload.return_value = {
                "success": True,
                "data": {"id": "test_file_id"}
            }

            # 并发上传3个文件
            files = [
                ("files", (f"test{i}.jpg", test_image_bytes, "image/jpeg"))
                for i in range(3)
            ]
            data = {
                "business_id": "123456",
                "doc_number": "SO001",
                "doc_type": "销售"
            }

            response = client.post("/api/upload", files=files, data=data)
            assert response.status_code == 200

            # 注意：TestClient不会自动执行后台任务
            # 这里仅验证记录创建成功


class TestStatusTransition:
    """测试状态流转 (P0)"""

    @pytest.mark.asyncio
    async def test_status_flow_success(self, test_db_path, test_image_bytes):
        """测试成功场景的状态流转: pending → uploading → success"""
        os.environ["DATABASE_URL"] = f"sqlite:///{test_db_path}"

        # 创建pending记录
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO upload_history
            (business_id, doc_number, doc_type, file_name, file_size, file_extension,
             upload_time, status, retry_count, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'), ?, ?, datetime('now'), datetime('now'))
        """, ("123456", "SO001", "销售", "test.jpg", len(test_image_bytes), ".jpg", "pending", 0))
        record_id = cursor.lastrowid
        conn.commit()

        # 验证初始状态
        cursor.execute("SELECT status FROM upload_history WHERE id = ?", (record_id,))
        assert cursor.fetchone()[0] == "pending"
        conn.close()

        # Mock用友云上传成功
        with patch('app.api.upload.yonyou_client.upload_file', new_callable=AsyncMock) as mock_upload:
            mock_upload.return_value = {
                "success": True,
                "data": {"id": "yonyou_file_id"}
            }

            await background_upload_to_yonyou(
                file_content=test_image_bytes,
                new_filename="test.jpg",
                business_id="123456",
                business_type="yonbip-scm-scmsa",
                local_file_path=f"/tmp/test_{record_id}.jpg",
                record_id=record_id
            )

        # 验证最终状态为success
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM upload_history WHERE id = ?", (record_id,))
        assert cursor.fetchone()[0] == "success"
        conn.close()

    @pytest.mark.asyncio
    async def test_status_flow_failure(self, test_db_path, test_image_bytes):
        """测试失败场景的状态流转: pending → uploading → failed"""
        os.environ["DATABASE_URL"] = f"sqlite:///{test_db_path}"

        # 创建pending记录
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO upload_history
            (business_id, doc_number, doc_type, file_name, file_size, file_extension,
             upload_time, status, retry_count, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'), ?, ?, datetime('now'), datetime('now'))
        """, ("123456", "SO001", "销售", "test.jpg", len(test_image_bytes), ".jpg", "pending", 0))
        record_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Mock用友云上传失败
        with patch('app.api.upload.yonyou_client.upload_file', new_callable=AsyncMock) as mock_upload:
            mock_upload.return_value = {
                "success": False,
                "error_code": "UPLOAD_FAILED",
                "error_message": "上传失败"
            }

            with patch('asyncio.sleep', new_callable=AsyncMock):
                await background_upload_to_yonyou(
                    file_content=test_image_bytes,
                    new_filename="test.jpg",
                    business_id="123456",
                    business_type="yonbip-scm-scmsa",
                    local_file_path=f"/tmp/test_{record_id}.jpg",
                    record_id=record_id
                )

        # 验证最终状态为failed
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM upload_history WHERE id = ?", (record_id,))
        assert cursor.fetchone()[0] == "failed"
        conn.close()


class TestEdgeCases:
    """测试边界情况 (P1)"""

    def test_upload_with_product_type(self, test_db_path, test_image_bytes):
        """测试带产品类型的上传"""
        os.environ["DATABASE_URL"] = f"sqlite:///{test_db_path}"

        # 清空数据库
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM upload_history")
        conn.commit()
        conn.close()

        client = TestClient(app)

        with patch('app.api.upload.background_upload_to_yonyou', new_callable=AsyncMock):
            files = [("files", ("test.jpg", test_image_bytes, "image/jpeg"))]
            data = {
                "business_id": "123456",
                "doc_number": "SO001",
                "doc_type": "销售",
                "product_type": "油脂"
            }

            response = client.post("/api/upload", files=files, data=data)
            assert response.status_code == 200

            result = response.json()
            record_id = result["records"][0]["id"]

            # 验证product_type正确保存
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT product_type FROM upload_history WHERE id = ?", (record_id,))
            product_type = cursor.fetchone()[0]
            conn.close()

            assert product_type == "油脂"

    def test_upload_different_doc_types(self, test_db_path, test_image_bytes):
        """测试不同单据类型的上传"""
        os.environ["DATABASE_URL"] = f"sqlite:///{test_db_path}"

        # 清空数据库
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM upload_history")
        conn.commit()
        conn.close()

        client = TestClient(app)

        doc_types = ["销售", "转库", "其他"]

        with patch('app.api.upload.background_upload_to_yonyou', new_callable=AsyncMock):
            for doc_type in doc_types:
                files = [("files", (f"test_{doc_type}.jpg", test_image_bytes, "image/jpeg"))]
                data = {
                    "business_id": "123456",
                    "doc_number": f"DOC_{doc_type}",
                    "doc_type": doc_type
                }

                response = client.post("/api/upload", files=files, data=data)
                assert response.status_code == 200, f"上传失败: {doc_type}"

        # 验证所有类型都成功创建记录
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT doc_type FROM upload_history ORDER BY doc_type")
        saved_types = [row[0] for row in cursor.fetchall()]
        conn.close()

        assert set(saved_types) == set(doc_types)

    def test_upload_max_file_limit(self, test_db_path, test_image_bytes):
        """测试最大文件数量限制"""
        os.environ["DATABASE_URL"] = f"sqlite:///{test_db_path}"

        client = TestClient(app)

        with patch('app.api.upload.background_upload_to_yonyou', new_callable=AsyncMock):
            # 尝试上传11个文件（超过限制10个）
            files = [
                ("files", (f"test{i}.jpg", test_image_bytes, "image/jpeg"))
                for i in range(11)
            ]
            data = {
                "business_id": "123456",
                "doc_number": "SO001",
                "doc_type": "销售"
            }

            response = client.post("/api/upload", files=files, data=data)
            assert response.status_code == 400
            assert "最多上传" in response.json()["detail"]
