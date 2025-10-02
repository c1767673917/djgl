"""测试历史查询API端点"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
import sqlite3

from app.main import app


client = TestClient(app)


class TestHistoryAPI:
    """测试历史查询API功能"""

    def test_get_history_with_records(self, test_db_path):
        """测试查询存在的上传历史记录"""
        # 准备测试数据
        conn = sqlite3.connect(test_db_path)
        cursor = conn.cursor()

        # 插入测试记录
        test_data = [
            ("123456", "test1.jpg", 1024, ".jpg", "success", None, None, "file_id_1", 0),
            ("123456", "test2.jpg", 2048, ".jpg", "success", None, None, "file_id_2", 0),
            ("123456", "test3.jpg", 1536, ".jpg", "failed", "40000", "上传失败", None, 2),
        ]

        for data in test_data:
            cursor.execute("""
                INSERT INTO upload_history
                (business_id, file_name, file_size, file_extension, status,
                 error_code, error_message, yonyou_file_id, retry_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, data)

        conn.commit()
        conn.close()

        # Mock数据库连接
        with patch('app.api.history.get_db_connection') as mock_db_conn:
            mock_db_conn.return_value = sqlite3.connect(test_db_path)

            response = client.get("/api/history/123456")

            assert response.status_code == 200
            result = response.json()

            assert result["business_id"] == "123456"
            assert result["total_count"] == 3
            assert result["success_count"] == 2
            assert result["failed_count"] == 1
            assert len(result["records"]) == 3

    def test_get_history_no_records(self, test_db_path):
        """测试查询不存在的业务单据"""
        with patch('app.api.history.get_db_connection') as mock_db_conn:
            mock_db_conn.return_value = sqlite3.connect(test_db_path)

            response = client.get("/api/history/999999")

            assert response.status_code == 200
            result = response.json()

            assert result["business_id"] == "999999"
            assert result["total_count"] == 0
            assert result["success_count"] == 0
            assert result["failed_count"] == 0
            assert result["records"] == []

    def test_get_history_record_fields(self, test_db_path):
        """测试返回记录包含所有必需字段"""
        conn = sqlite3.connect(test_db_path)
        cursor = conn.cursor()

        # 插入一条完整记录
        cursor.execute("""
            INSERT INTO upload_history
            (business_id, file_name, file_size, file_extension, status,
             error_code, error_message, yonyou_file_id, retry_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ("123456", "test.jpg", 1024, ".jpg", "success", None, None, "file_id_123", 1))

        conn.commit()
        conn.close()

        with patch('app.api.history.get_db_connection') as mock_db_conn:
            mock_db_conn.return_value = sqlite3.connect(test_db_path)

            response = client.get("/api/history/123456")

            assert response.status_code == 200
            result = response.json()
            record = result["records"][0]

            # 验证所有字段都存在
            assert "id" in record
            assert "file_name" in record
            assert "file_size" in record
            assert "file_extension" in record
            assert "upload_time" in record
            assert "status" in record
            assert "error_code" in record
            assert "error_message" in record
            assert "yonyou_file_id" in record
            assert "retry_count" in record

            # 验证字段值
            assert record["file_name"] == "test.jpg"
            assert record["file_size"] == 1024
            assert record["file_extension"] == ".jpg"
            assert record["status"] == "success"
            assert record["yonyou_file_id"] == "file_id_123"
            assert record["retry_count"] == 1

    def test_get_history_order_by_time(self, test_db_path):
        """测试记录按上传时间倒序排列"""
        import time

        conn = sqlite3.connect(test_db_path)
        cursor = conn.cursor()

        # 插入多条记录(间隔插入确保时间不同)
        for i in range(3):
            cursor.execute("""
                INSERT INTO upload_history
                (business_id, file_name, file_size, file_extension, status,
                 error_code, error_message, yonyou_file_id, retry_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, ("123456", f"test{i}.jpg", 1024, ".jpg", "success", None, None, f"file_id_{i}", 0))
            conn.commit()
            time.sleep(0.01)  # 确保时间戳不同

        conn.close()

        with patch('app.api.history.get_db_connection') as mock_db_conn:
            mock_db_conn.return_value = sqlite3.connect(test_db_path)

            response = client.get("/api/history/123456")

            assert response.status_code == 200
            result = response.json()

            # 最新的记录应该在前面
            assert result["records"][0]["file_name"] == "test2.jpg"
            assert result["records"][1]["file_name"] == "test1.jpg"
            assert result["records"][2]["file_name"] == "test0.jpg"

    def test_get_history_multiple_business_ids(self, test_db_path):
        """测试不同业务单据的记录隔离"""
        conn = sqlite3.connect(test_db_path)
        cursor = conn.cursor()

        # 插入不同业务单据的记录
        test_data = [
            ("123456", "test1.jpg", 1024, ".jpg", "success", None, None, "file_id_1", 0),
            ("123456", "test2.jpg", 2048, ".jpg", "success", None, None, "file_id_2", 0),
            ("654321", "test3.jpg", 1536, ".jpg", "success", None, None, "file_id_3", 0),
        ]

        for data in test_data:
            cursor.execute("""
                INSERT INTO upload_history
                (business_id, file_name, file_size, file_extension, status,
                 error_code, error_message, yonyou_file_id, retry_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, data)

        conn.commit()
        conn.close()

        with patch('app.api.history.get_db_connection') as mock_db_conn:
            mock_db_conn.return_value = sqlite3.connect(test_db_path)

            # 查询第一个业务单据
            response1 = client.get("/api/history/123456")
            result1 = response1.json()
            assert result1["total_count"] == 2

            # 查询第二个业务单据
            response2 = client.get("/api/history/654321")
            result2 = response2.json()
            assert result2["total_count"] == 1

    def test_get_history_sql_injection_protection(self, test_db_path):
        """测试SQL注入防护"""
        conn = sqlite3.connect(test_db_path)
        cursor = conn.cursor()

        # 插入测试数据
        cursor.execute("""
            INSERT INTO upload_history
            (business_id, file_name, file_size, file_extension, status,
             error_code, error_message, yonyou_file_id, retry_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ("123456", "test.jpg", 1024, ".jpg", "success", None, None, "file_id_1", 0))

        conn.commit()
        conn.close()

        with patch('app.api.history.get_db_connection') as mock_db_conn:
            mock_db_conn.return_value = sqlite3.connect(test_db_path)

            # 尝试SQL注入
            malicious_id = "123456' OR '1'='1"
            response = client.get(f"/api/history/{malicious_id}")

            assert response.status_code == 200
            result = response.json()

            # 应该返回空结果,而不是所有记录
            assert result["total_count"] == 0

    def test_get_history_success_failed_count(self, test_db_path):
        """测试成功/失败计数准确性"""
        conn = sqlite3.connect(test_db_path)
        cursor = conn.cursor()

        # 插入混合状态的记录
        test_data = [
            ("123456", "test1.jpg", 1024, ".jpg", "success", None, None, "file_id_1", 0),
            ("123456", "test2.jpg", 2048, ".jpg", "failed", "40000", "错误", None, 2),
            ("123456", "test3.jpg", 1536, ".jpg", "success", None, None, "file_id_3", 0),
            ("123456", "test4.jpg", 2048, ".jpg", "failed", "40000", "错误", None, 1),
            ("123456", "test5.jpg", 1024, ".jpg", "success", None, None, "file_id_5", 0),
        ]

        for data in test_data:
            cursor.execute("""
                INSERT INTO upload_history
                (business_id, file_name, file_size, file_extension, status,
                 error_code, error_message, yonyou_file_id, retry_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, data)

        conn.commit()
        conn.close()

        with patch('app.api.history.get_db_connection') as mock_db_conn:
            mock_db_conn.return_value = sqlite3.connect(test_db_path)

            response = client.get("/api/history/123456")

            assert response.status_code == 200
            result = response.json()

            assert result["total_count"] == 5
            assert result["success_count"] == 3
            assert result["failed_count"] == 2
