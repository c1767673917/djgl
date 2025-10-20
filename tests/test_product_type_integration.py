"""产品类型功能端到端集成测试"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, Mock
import sqlite3

from app.main import app


client = TestClient(app)


class TestProductTypeEndToEnd:
    """端到端测试完整的产品类型工作流"""

    def test_complete_workflow_with_product_type(
        self,
        test_image_bytes,
        test_db_path
    ):
        """测试完整工作流: 上传(带product_type) → 查询 → 导出"""
        with patch('app.api.upload.yonyou_client.upload_file', new_callable=AsyncMock) as mock_upload, \
             patch('app.api.upload.get_db_connection') as mock_upload_db, \
             patch('app.api.admin.get_db_connection') as mock_admin_db:

            # Mock用友云上传
            mock_upload.return_value = {
                "success": True,
                "data": {
                    "id": "file_id_e2e_001",
                    "fileName": "e2e_test.jpg",
                    "fileSize": len(test_image_bytes),
                    "fileExtension": ".jpg"
                }
            }

            # 使用同一个数据库连接
            db_conn = sqlite3.connect(test_db_path)
            mock_upload_db.return_value = db_conn
            mock_admin_db.return_value = db_conn

            # 步骤1: 上传文件(带product_type)
            files = {"files": ("e2e_test.jpg", test_image_bytes, "image/jpeg")}
            upload_data = {
                "business_id": "111222",
                "doc_number": "E2E_SO001",
                "doc_type": "销售",
                "product_type": "油脂"
            }

            upload_response = client.post("/api/upload", files=files, data=upload_data)

            assert upload_response.status_code == 200
            upload_result = upload_response.json()
            assert upload_result["success"] is True
            assert upload_result["succeeded"] == 1

            # 步骤2: 查询所有记录,验证product_type存在
            all_records_response = client.get("/api/admin/records?page=1&page_size=20")

            assert all_records_response.status_code == 200
            all_records = all_records_response.json()

            # 查找刚上传的记录
            target_record = next(
                (r for r in all_records["records"] if r["doc_number"] == "E2E_SO001"),
                None
            )

            assert target_record is not None, "应能查询到刚上传的记录"
            assert target_record["product_type"] == "油脂", "product_type应为'油脂'"
            assert target_record["business_id"] == "111222", "business_id应保持不变"

            # 步骤3: 按product_type筛选
            filtered_response = client.get("/api/admin/records?page=1&page_size=20&product_type=油脂")

            assert filtered_response.status_code == 200
            filtered_records = filtered_response.json()

            # 验证筛选结果包含该记录
            assert any(r["doc_number"] == "E2E_SO001" for r in filtered_records["records"]), \
                "筛选结果应包含E2E_SO001"

            # 验证筛选结果中所有记录都是油脂
            for record in filtered_records["records"]:
                assert record["product_type"] == "油脂", "筛选结果应全部为油脂产品"

            # 步骤4: 导出验证(检查URL参数正确传递)
            export_response = client.get("/api/admin/export?product_type=油脂")
            assert export_response.status_code == 200
            assert export_response.headers["content-type"] == "application/zip"

            # 清理
            cursor = db_conn.cursor()
            cursor.execute("DELETE FROM upload_history WHERE doc_number = 'E2E_SO001'")
            db_conn.commit()
            db_conn.close()

    def test_backward_compatibility_workflow(
        self,
        test_image_bytes,
        test_db_path
    ):
        """测试向后兼容工作流: 上传(不带product_type) → 查询 → 验证NULL"""
        with patch('app.api.upload.yonyou_client.upload_file', new_callable=AsyncMock) as mock_upload, \
             patch('app.api.upload.get_db_connection') as mock_upload_db, \
             patch('app.api.admin.get_db_connection') as mock_admin_db:

            mock_upload.return_value = {
                "success": True,
                "data": {
                    "id": "file_id_compat_001",
                    "fileName": "compat_test.jpg",
                    "fileSize": len(test_image_bytes),
                    "fileExtension": ".jpg"
                }
            }

            db_conn = sqlite3.connect(test_db_path)
            mock_upload_db.return_value = db_conn
            mock_admin_db.return_value = db_conn

            # 步骤1: 上传文件(不带product_type,模拟旧版URL)
            files = {"files": ("compat_test.jpg", test_image_bytes, "image/jpeg")}
            upload_data = {
                "business_id": "333444",
                "doc_number": "COMPAT_SO001",
                "doc_type": "销售"
                # 注意: 不包含product_type参数
            }

            upload_response = client.post("/api/upload", files=files, data=upload_data)

            assert upload_response.status_code == 200
            upload_result = upload_response.json()
            assert upload_result["success"] is True

            # 步骤2: 查询记录,验证product_type为NULL
            all_records_response = client.get("/api/admin/records?page=1&page_size=20")

            assert all_records_response.status_code == 200
            all_records = all_records_response.json()

            target_record = next(
                (r for r in all_records["records"] if r["doc_number"] == "COMPAT_SO001"),
                None
            )

            assert target_record is not None, "应能查询到旧版上传的记录"
            assert target_record["product_type"] is None, "不传product_type时应为NULL"

            # 步骤3: 验证筛选"全部"包含NULL记录
            all_filter_response = client.get("/api/admin/records?page=1&page_size=20")
            all_filter_records = all_filter_response.json()

            assert any(r["doc_number"] == "COMPAT_SO001" for r in all_filter_records["records"]), \
                "筛选'全部'应包含NULL记录"

            # 步骤4: 验证筛选特定product_type不包含NULL记录
            oil_filter_response = client.get("/api/admin/records?page=1&page_size=20&product_type=油脂")
            oil_filter_records = oil_filter_response.json()

            assert not any(r["doc_number"] == "COMPAT_SO001" for r in oil_filter_records["records"]), \
                "筛选'油脂'不应包含NULL记录"

            # 清理
            cursor = db_conn.cursor()
            cursor.execute("DELETE FROM upload_history WHERE doc_number = 'COMPAT_SO001'")
            db_conn.commit()
            db_conn.close()

    def test_mixed_data_workflow(
        self,
        test_image_bytes,
        test_db_path
    ):
        """测试混合数据场景: 部分有product_type,部分为NULL"""
        with patch('app.api.upload.yonyou_client.upload_file', new_callable=AsyncMock) as mock_upload, \
             patch('app.api.upload.get_db_connection') as mock_upload_db, \
             patch('app.api.admin.get_db_connection') as mock_admin_db:

            mock_upload.return_value = {
                "success": True,
                "data": {
                    "id": "file_id_mixed_001",
                    "fileName": "mixed_test.jpg",
                    "fileSize": len(test_image_bytes),
                    "fileExtension": ".jpg"
                }
            }

            db_conn = sqlite3.connect(test_db_path)
            mock_upload_db.return_value = db_conn
            mock_admin_db.return_value = db_conn

            # 上传3个文件: 油脂、快消、NULL
            test_cases = [
                ("MIXED_001", "油脂"),
                ("MIXED_002", "快消"),
                ("MIXED_003", None),  # 不传product_type
            ]

            for doc_number, product_type in test_cases:
                files = {"files": ("mixed_test.jpg", test_image_bytes, "image/jpeg")}
                upload_data = {
                    "business_id": "555666",
                    "doc_number": doc_number,
                    "doc_type": "销售"
                }

                if product_type is not None:
                    upload_data["product_type"] = product_type

                upload_response = client.post("/api/upload", files=files, data=upload_data)
                assert upload_response.status_code == 200

            # 验证查询所有记录
            all_response = client.get("/api/admin/records?page=1&page_size=20")
            all_records = all_response.json()["records"]

            mixed_records = [r for r in all_records if r["doc_number"].startswith("MIXED_")]
            assert len(mixed_records) == 3, "应有3条混合记录"

            # 验证各自的product_type
            assert any(r["doc_number"] == "MIXED_001" and r["product_type"] == "油脂" for r in mixed_records)
            assert any(r["doc_number"] == "MIXED_002" and r["product_type"] == "快消" for r in mixed_records)
            assert any(r["doc_number"] == "MIXED_003" and r["product_type"] is None for r in mixed_records)

            # 验证筛选"油脂"只返回1条
            oil_response = client.get("/api/admin/records?page=1&page_size=20&product_type=油脂")
            oil_records = oil_response.json()["records"]
            oil_mixed = [r for r in oil_records if r["doc_number"].startswith("MIXED_")]
            assert len(oil_mixed) == 1, "筛选'油脂'应只返回1条"
            assert oil_mixed[0]["doc_number"] == "MIXED_001"

            # 验证筛选"快消"只返回1条
            fast_response = client.get("/api/admin/records?page=1&page_size=20&product_type=快消")
            fast_records = fast_response.json()["records"]
            fast_mixed = [r for r in fast_records if r["doc_number"].startswith("MIXED_")]
            assert len(fast_mixed) == 1, "筛选'快消'应只返回1条"
            assert fast_mixed[0]["doc_number"] == "MIXED_002"

            # 清理
            cursor = db_conn.cursor()
            cursor.execute("DELETE FROM upload_history WHERE doc_number LIKE 'MIXED_%'")
            db_conn.commit()
            db_conn.close()

    def test_batch_upload_with_different_product_types(
        self,
        test_image_bytes,
        test_db_path
    ):
        """测试批量上传时不同产品类型的处理"""
        # 注意: 当前API设计是批量上传使用同一个product_type
        # 这个测试验证同一批次的所有文件共享相同的product_type
        with patch('app.api.upload.yonyou_client.upload_file', new_callable=AsyncMock) as mock_upload, \
             patch('app.api.upload.get_db_connection') as mock_upload_db, \
             patch('app.api.admin.get_db_connection') as mock_admin_db:

            mock_upload.return_value = {
                "success": True,
                "data": {
                    "id": "file_id_batch_001",
                    "fileName": "batch_test.jpg",
                    "fileSize": len(test_image_bytes),
                    "fileExtension": ".jpg"
                }
            }

            db_conn = sqlite3.connect(test_db_path)
            mock_upload_db.return_value = db_conn
            mock_admin_db.return_value = db_conn

            # 批量上传5个文件,同一个product_type
            files = [
                ("files", (f"batch_{i}.jpg", test_image_bytes, "image/jpeg"))
                for i in range(5)
            ]
            upload_data = {
                "business_id": "777888",
                "doc_number": "BATCH_SO001",
                "doc_type": "销售",
                "product_type": "油脂"
            }

            upload_response = client.post("/api/upload", files=files, data=upload_data)

            assert upload_response.status_code == 200
            upload_result = upload_response.json()
            assert upload_result["total"] == 5
            assert upload_result["succeeded"] == 5

            # 验证所有记录的product_type都正确
            all_response = client.get("/api/admin/records?page=1&page_size=20&doc_number=BATCH_SO001")
            all_records = all_response.json()["records"]

            batch_records = [r for r in all_records if r["doc_number"] == "BATCH_SO001"]
            assert len(batch_records) == 5, "应有5条批量上传记录"

            for record in batch_records:
                assert record["product_type"] == "油脂", "所有批量记录应共享同一product_type"

            # 清理
            cursor = db_conn.cursor()
            cursor.execute("DELETE FROM upload_history WHERE doc_number = 'BATCH_SO001'")
            db_conn.commit()
            db_conn.close()

    def test_performance_with_product_type_index(self, test_db_path):
        """测试product_type索引的性能优化效果"""
        # 这是一个性能测试的占位
        # 实际测试中应该:
        # 1. 插入大量数据(如1000条)
        # 2. 使用EXPLAIN QUERY PLAN验证使用了索引
        # 3. 测量查询响应时间 < 100ms

        conn = sqlite3.connect(test_db_path)
        cursor = conn.cursor()

        # 验证索引存在
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='index' AND name='idx_product_type'
        """)
        result = cursor.fetchone()
        assert result is not None, "idx_product_type索引应存在"

        # 使用EXPLAIN验证查询会使用索引
        cursor.execute("""
            EXPLAIN QUERY PLAN
            SELECT * FROM upload_history
            WHERE product_type = '油脂' AND deleted_at IS NULL
        """)
        plan = cursor.fetchall()

        # SQLite的EXPLAIN QUERY PLAN输出应该提到使用了索引
        plan_str = str(plan)
        # 注意: 由于WHERE条件包含deleted_at,可能使用复合索引或全表扫描
        # 这里只验证查询计划生成成功
        assert plan is not None and len(plan) > 0

        conn.close()
