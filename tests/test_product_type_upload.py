"""测试上传接口的产品类型参数功能"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, Mock
import sqlite3

from app.main import app


client = TestClient(app)


class TestUploadWithProductType:
    """测试上传接口的产品类型参数"""

    def test_upload_with_product_type_oil(self, test_image_bytes, test_db_path):
        """测试带product_type='油脂'参数的上传"""
        with patch('app.api.upload.yonyou_client.upload_file', new_callable=AsyncMock) as mock_upload, \
             patch('app.api.upload.get_db_connection') as mock_db_conn:

            # Mock用友云上传成功
            mock_upload.return_value = {
                "success": True,
                "data": {
                    "id": "file_id_oil_123",
                    "fileName": "test_oil.jpg",
                    "fileSize": len(test_image_bytes),
                    "fileExtension": ".jpg"
                }
            }

            # Mock数据库连接
            db_conn = sqlite3.connect(test_db_path)
            mock_db_conn.return_value = db_conn

            # 上传带product_type的文件
            files = {"files": ("test_oil.jpg", test_image_bytes, "image/jpeg")}
            data = {
                "business_id": "123456",
                "doc_number": "SO20250120001",
                "doc_type": "销售",
                "product_type": "油脂"
            }

            response = client.post("/api/upload", files=files, data=data)

            assert response.status_code == 200
            result = response.json()
            assert result["success"] is True
            assert result["succeeded"] == 1
            assert result["failed"] == 0

            # 验证数据库中product_type正确存储
            cursor = db_conn.cursor()
            cursor.execute("""
                SELECT product_type FROM upload_history
                WHERE doc_number = 'SO20250120001'
            """)
            row = cursor.fetchone()

            assert row is not None, "数据库未存储上传记录"
            assert row[0] == "油脂", f"product_type应为'油脂', 实际为{row[0]}"

            db_conn.close()

    def test_upload_with_product_type_fast_moving(self, test_image_bytes, test_db_path):
        """测试带product_type='快消'参数的上传"""
        with patch('app.api.upload.yonyou_client.upload_file', new_callable=AsyncMock) as mock_upload, \
             patch('app.api.upload.get_db_connection') as mock_db_conn:

            mock_upload.return_value = {
                "success": True,
                "data": {
                    "id": "file_id_fast_123",
                    "fileName": "test_fast.jpg",
                    "fileSize": len(test_image_bytes),
                    "fileExtension": ".jpg"
                }
            }

            db_conn = sqlite3.connect(test_db_path)
            mock_db_conn.return_value = db_conn

            files = {"files": ("test_fast.jpg", test_image_bytes, "image/jpeg")}
            data = {
                "business_id": "123456",
                "doc_number": "SO20250120002",
                "doc_type": "销售",
                "product_type": "快消"
            }

            response = client.post("/api/upload", files=files, data=data)

            assert response.status_code == 200
            result = response.json()
            assert result["success"] is True

            # 验证数据库
            cursor = db_conn.cursor()
            cursor.execute("""
                SELECT product_type FROM upload_history
                WHERE doc_number = 'SO20250120002'
            """)
            row = cursor.fetchone()

            assert row[0] == "快消", f"product_type应为'快消', 实际为{row[0]}"

            db_conn.close()

    def test_upload_without_product_type(self, test_image_bytes, test_db_path):
        """测试不带product_type参数的上传（向后兼容）"""
        with patch('app.api.upload.yonyou_client.upload_file', new_callable=AsyncMock) as mock_upload, \
             patch('app.api.upload.get_db_connection') as mock_db_conn:

            mock_upload.return_value = {
                "success": True,
                "data": {
                    "id": "file_id_no_pt_123",
                    "fileName": "test_no_pt.jpg",
                    "fileSize": len(test_image_bytes),
                    "fileExtension": ".jpg"
                }
            }

            db_conn = sqlite3.connect(test_db_path)
            mock_db_conn.return_value = db_conn

            # 不提供product_type参数
            files = {"files": ("test_no_pt.jpg", test_image_bytes, "image/jpeg")}
            data = {
                "business_id": "123456",
                "doc_number": "SO20250120003",
                "doc_type": "销售"
                # 注意：不包含product_type参数
            }

            response = client.post("/api/upload", files=files, data=data)

            # 验证上传成功（向后兼容）
            assert response.status_code == 200
            result = response.json()
            assert result["success"] is True

            # 验证数据库中product_type为NULL
            cursor = db_conn.cursor()
            cursor.execute("""
                SELECT product_type FROM upload_history
                WHERE doc_number = 'SO20250120003'
            """)
            row = cursor.fetchone()

            assert row is not None, "数据库未存储上传记录"
            assert row[0] is None, f"不传product_type时应为NULL, 实际为{row[0]}"

            db_conn.close()

    def test_upload_with_custom_product_type(self, test_image_bytes, test_db_path):
        """测试自定义产品类型值（非预设值）"""
        with patch('app.api.upload.yonyou_client.upload_file', new_callable=AsyncMock) as mock_upload, \
             patch('app.api.upload.get_db_connection') as mock_db_conn:

            mock_upload.return_value = {
                "success": True,
                "data": {
                    "id": "file_id_custom_123",
                    "fileName": "test_custom.jpg",
                    "fileSize": len(test_image_bytes),
                    "fileExtension": ".jpg"
                }
            }

            db_conn = sqlite3.connect(test_db_path)
            mock_db_conn.return_value = db_conn

            # 使用预设之外的值
            files = {"files": ("test_custom.jpg", test_image_bytes, "image/jpeg")}
            data = {
                "business_id": "123456",
                "doc_number": "SO20250120004",
                "doc_type": "销售",
                "product_type": "调味品"  # 自定义值
            }

            response = client.post("/api/upload", files=files, data=data)

            # 验证上传成功（允许任意值）
            assert response.status_code == 200
            result = response.json()
            assert result["success"] is True

            # 验证数据库正确存储自定义值
            cursor = db_conn.cursor()
            cursor.execute("""
                SELECT product_type FROM upload_history
                WHERE doc_number = 'SO20250120004'
            """)
            row = cursor.fetchone()

            assert row[0] == "调味品", f"product_type应为'调味品', 实际为{row[0]}"

            db_conn.close()

    def test_upload_with_empty_string_product_type(self, test_image_bytes, test_db_path):
        """测试product_type为空字符串"""
        with patch('app.api.upload.yonyou_client.upload_file', new_callable=AsyncMock) as mock_upload, \
             patch('app.api.upload.get_db_connection') as mock_db_conn:

            mock_upload.return_value = {
                "success": True,
                "data": {
                    "id": "file_id_empty_123",
                    "fileName": "test_empty.jpg",
                    "fileSize": len(test_image_bytes),
                    "fileExtension": ".jpg"
                }
            }

            db_conn = sqlite3.connect(test_db_path)
            mock_db_conn.return_value = db_conn

            files = {"files": ("test_empty.jpg", test_image_bytes, "image/jpeg")}
            data = {
                "business_id": "123456",
                "doc_number": "SO20250120005",
                "doc_type": "销售",
                "product_type": ""  # 空字符串
            }

            response = client.post("/api/upload", files=files, data=data)

            assert response.status_code == 200
            result = response.json()
            assert result["success"] is True

            # 验证数据库存储空字符串
            cursor = db_conn.cursor()
            cursor.execute("""
                SELECT product_type FROM upload_history
                WHERE doc_number = 'SO20250120005'
            """)
            row = cursor.fetchone()

            assert row[0] == "", f"product_type应为空字符串, 实际为{row[0]}"

            db_conn.close()

    def test_upload_with_special_characters_product_type(self, test_image_bytes, test_db_path):
        """测试product_type包含特殊字符（防SQL注入）"""
        with patch('app.api.upload.yonyou_client.upload_file', new_callable=AsyncMock) as mock_upload, \
             patch('app.api.upload.get_db_connection') as mock_db_conn:

            mock_upload.return_value = {
                "success": True,
                "data": {
                    "id": "file_id_special_123",
                    "fileName": "test_special.jpg",
                    "fileSize": len(test_image_bytes),
                    "fileExtension": ".jpg"
                }
            }

            db_conn = sqlite3.connect(test_db_path)
            mock_db_conn.return_value = db_conn

            # 测试特殊字符
            special_value = "产品'; DROP TABLE upload_history; --"

            files = {"files": ("test_special.jpg", test_image_bytes, "image/jpeg")}
            data = {
                "business_id": "123456",
                "doc_number": "SO20250120006",
                "doc_type": "销售",
                "product_type": special_value
            }

            response = client.post("/api/upload", files=files, data=data)

            assert response.status_code == 200
            result = response.json()
            assert result["success"] is True

            # 验证数据库仍然存在（防SQL注入）
            cursor = db_conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='upload_history'")
            assert cursor.fetchone() is not None, "表不应被删除（SQL注入测试）"

            # 验证特殊字符正确存储
            cursor.execute("""
                SELECT product_type FROM upload_history
                WHERE doc_number = 'SO20250120006'
            """)
            row = cursor.fetchone()

            assert row[0] == special_value, f"特殊字符应正确存储"

            db_conn.close()

    def test_upload_batch_with_product_type(self, test_image_bytes, test_db_path):
        """测试批量上传时product_type正确存储"""
        with patch('app.api.upload.yonyou_client.upload_file', new_callable=AsyncMock) as mock_upload, \
             patch('app.api.upload.get_db_connection') as mock_db_conn:

            mock_upload.return_value = {
                "success": True,
                "data": {
                    "id": "file_id_batch_123",
                    "fileName": "test_batch.jpg",
                    "fileSize": len(test_image_bytes),
                    "fileExtension": ".jpg"
                }
            }

            db_conn = sqlite3.connect(test_db_path)
            mock_db_conn.return_value = db_conn

            # 批量上传5个文件,同一个product_type
            files = [
                ("files", (f"test_batch_{i}.jpg", test_image_bytes, "image/jpeg"))
                for i in range(5)
            ]
            data = {
                "business_id": "123456",
                "doc_number": "SO20250120007",
                "doc_type": "销售",
                "product_type": "油脂"
            }

            response = client.post("/api/upload", files=files, data=data)

            assert response.status_code == 200
            result = response.json()
            assert result["success"] is True
            assert result["total"] == 5
            assert result["succeeded"] == 5

            # 验证所有记录的product_type都正确
            cursor = db_conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM upload_history
                WHERE doc_number = 'SO20250120007' AND product_type = '油脂'
            """)
            count = cursor.fetchone()[0]

            assert count == 5, f"应有5条product_type='油脂'的记录, 实际{count}条"

            db_conn.close()

    def test_upload_preserves_business_id(self, test_image_bytes, test_db_path):
        """测试上传时business_id仍然正确存储（两者共存）"""
        with patch('app.api.upload.yonyou_client.upload_file', new_callable=AsyncMock) as mock_upload, \
             patch('app.api.upload.get_db_connection') as mock_db_conn:

            mock_upload.return_value = {
                "success": True,
                "data": {
                    "id": "file_id_both_123",
                    "fileName": "test_both.jpg",
                    "fileSize": len(test_image_bytes),
                    "fileExtension": ".jpg"
                }
            }

            db_conn = sqlite3.connect(test_db_path)
            mock_db_conn.return_value = db_conn

            files = {"files": ("test_both.jpg", test_image_bytes, "image/jpeg")}
            data = {
                "business_id": "999888",
                "doc_number": "SO20250120008",
                "doc_type": "销售",
                "product_type": "快消"
            }

            response = client.post("/api/upload", files=files, data=data)

            assert response.status_code == 200

            # 验证business_id和product_type都正确存储
            cursor = db_conn.cursor()
            cursor.execute("""
                SELECT business_id, product_type FROM upload_history
                WHERE doc_number = 'SO20250120008'
            """)
            row = cursor.fetchone()

            assert row is not None, "记录未存储"
            assert row[0] == "999888", f"business_id应为'999888', 实际为{row[0]}"
            assert row[1] == "快消", f"product_type应为'快消', 实际为{row[1]}"

            db_conn.close()
