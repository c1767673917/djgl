"""测试管理接口的产品类型筛选功能"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
import sqlite3

from app.main import app


client = TestClient(app)


class TestAdminProductTypeFilter:
    """测试管理页面的产品类型筛选功能"""

    @pytest.fixture
    def setup_test_data(self, test_db_path):
        """准备测试数据"""
        conn = sqlite3.connect(test_db_path)
        cursor = conn.cursor()

        from app.core.timezone import get_beijing_now_naive
        beijing_now = get_beijing_now_naive().isoformat()

        # 插入测试数据
        test_records = [
            ("123456", "SO001", "销售", "油脂", "file1.jpg", 1024, ".jpg", "success"),
            ("123457", "SO002", "销售", "油脂", "file2.jpg", 2048, ".jpg", "success"),
            ("123458", "SO003", "销售", "快消", "file3.jpg", 3072, ".jpg", "success"),
            ("123459", "SO004", "转库", "快消", "file4.jpg", 4096, ".jpg", "success"),
            ("123460", "SO005", "销售", None, "file5.jpg", 5120, ".jpg", "success"),  # NULL值
            ("123461", "SO006", "销售", "", "file6.jpg", 6144, ".jpg", "success"),  # 空字符串
        ]

        for record in test_records:
            cursor.execute("""
                INSERT INTO upload_history
                (business_id, doc_number, doc_type, product_type, file_name, file_size,
                 file_extension, upload_time, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, record + (beijing_now, beijing_now))

        conn.commit()

        yield conn

        # 清理测试数据
        cursor.execute("DELETE FROM upload_history WHERE doc_number LIKE 'SO00%'")
        conn.commit()
        conn.close()

    def test_get_records_without_product_type_filter(self, setup_test_data):
        """测试不带product_type筛选参数（返回所有记录）"""
        with patch('app.api.admin.get_db_connection') as mock_db_conn:
            mock_db_conn.return_value = setup_test_data

            response = client.get("/api/admin/records?page=1&page_size=20")

            assert response.status_code == 200
            result = response.json()

            # 验证返回所有成功记录（包括NULL和空字符串）
            assert result["total"] == 6, f"应返回6条记录,实际{result['total']}条"
            assert len(result["records"]) == 6

            # 验证返回的记录包含product_type字段
            for record in result["records"]:
                assert "product_type" in record, "记录应包含product_type字段"

    def test_filter_by_product_type_oil(self, setup_test_data):
        """测试筛选product_type='油脂'"""
        with patch('app.api.admin.get_db_connection') as mock_db_conn:
            mock_db_conn.return_value = setup_test_data

            response = client.get("/api/admin/records?page=1&page_size=20&product_type=油脂")

            assert response.status_code == 200
            result = response.json()

            # 验证只返回油脂产品
            assert result["total"] == 2, f"应返回2条油脂记录,实际{result['total']}条"
            assert len(result["records"]) == 2

            # 验证所有记录的product_type都是"油脂"
            for record in result["records"]:
                assert record["product_type"] == "油脂", f"product_type应为'油脂',实际为{record['product_type']}"

    def test_filter_by_product_type_fast_moving(self, setup_test_data):
        """测试筛选product_type='快消'"""
        with patch('app.api.admin.get_db_connection') as mock_db_conn:
            mock_db_conn.return_value = setup_test_data

            response = client.get("/api/admin/records?page=1&page_size=20&product_type=快消")

            assert response.status_code == 200
            result = response.json()

            # 验证只返回快消产品
            assert result["total"] == 2, f"应返回2条快消记录,实际{result['total']}条"

            # 验证所有记录的product_type都是"快消"
            for record in result["records"]:
                assert record["product_type"] == "快消", f"product_type应为'快消',实际为{record['product_type']}"

    def test_filter_excludes_null_product_type(self, setup_test_data):
        """测试筛选特定product_type时不包含NULL值"""
        with patch('app.api.admin.get_db_connection') as mock_db_conn:
            mock_db_conn.return_value = setup_test_data

            response = client.get("/api/admin/records?page=1&page_size=20&product_type=油脂")

            assert response.status_code == 200
            result = response.json()

            # 验证返回的记录中没有NULL值
            for record in result["records"]:
                assert record["product_type"] is not None, "筛选时不应包含NULL值记录"
                assert record["product_type"] != "", "筛选时不应包含空字符串记录"

    def test_combine_product_type_and_doc_type_filter(self, setup_test_data):
        """测试同时使用product_type和doc_type筛选"""
        with patch('app.api.admin.get_db_connection') as mock_db_conn:
            mock_db_conn.return_value = setup_test_data

            # 筛选：销售 + 油脂
            response = client.get("/api/admin/records?page=1&page_size=20&doc_type=销售&product_type=油脂")

            assert response.status_code == 200
            result = response.json()

            # 验证返回2条记录（SO001和SO002）
            assert result["total"] == 2, f"应返回2条记录,实际{result['total']}条"

            # 验证所有记录同时满足两个条件
            for record in result["records"]:
                assert record["doc_type"] == "销售", f"doc_type应为'销售'"
                assert record["product_type"] == "油脂", f"product_type应为'油脂'"

    def test_combine_product_type_and_search_filter(self, setup_test_data):
        """测试同时使用product_type和search筛选"""
        with patch('app.api.admin.get_db_connection') as mock_db_conn:
            mock_db_conn.return_value = setup_test_data

            # 搜索"SO00" + 筛选"快消"
            response = client.get("/api/admin/records?page=1&page_size=20&search=SO00&product_type=快消")

            assert response.status_code == 200
            result = response.json()

            # 验证返回2条快消记录（SO003和SO004）
            assert result["total"] == 2, f"应返回2条记录,实际{result['total']}条"

            for record in result["records"]:
                assert record["product_type"] == "快消"
                assert "SO00" in record["doc_number"]

    def test_response_includes_product_type_field(self, setup_test_data):
        """测试响应数据包含product_type字段"""
        with patch('app.api.admin.get_db_connection') as mock_db_conn:
            mock_db_conn.return_value = setup_test_data

            response = client.get("/api/admin/records?page=1&page_size=20")

            assert response.status_code == 200
            result = response.json()

            assert len(result["records"]) > 0, "应有记录返回"

            # 验证所有记录都包含product_type字段
            for record in result["records"]:
                assert "product_type" in record, "记录缺少product_type字段"

            # 验证不同值的正确性
            product_types = {r["product_type"] for r in result["records"]}
            assert "油脂" in product_types
            assert "快消" in product_types
            assert None in product_types  # NULL值
            assert "" in product_types  # 空字符串

    def test_null_product_type_displayed_correctly(self, setup_test_data):
        """测试NULL值在响应中正确处理"""
        with patch('app.api.admin.get_db_connection') as mock_db_conn:
            mock_db_conn.return_value = setup_test_data

            response = client.get("/api/admin/records?page=1&page_size=20")

            assert response.status_code == 200
            result = response.json()

            # 查找doc_number=SO005的记录（product_type=NULL）
            null_record = next((r for r in result["records"] if r["doc_number"] == "SO005"), None)

            assert null_record is not None, "应找到SO005记录"
            assert null_record["product_type"] is None, f"NULL值应为None,实际为{null_record['product_type']}"

    def test_pagination_with_product_type_filter(self, setup_test_data):
        """测试带product_type筛选的分页功能"""
        with patch('app.api.admin.get_db_connection') as mock_db_conn:
            mock_db_conn.return_value = setup_test_data

            # 第1页,每页1条
            response = client.get("/api/admin/records?page=1&page_size=1&product_type=油脂")

            assert response.status_code == 200
            result = response.json()

            assert result["total"] == 2, "油脂总共2条记录"
            assert result["page"] == 1
            assert result["page_size"] == 1
            assert result["total_pages"] == 2, "应有2页"
            assert len(result["records"]) == 1, "第1页应返回1条记录"

            # 第2页
            response2 = client.get("/api/admin/records?page=2&page_size=1&product_type=油脂")
            result2 = response2.json()

            assert result2["page"] == 2
            assert len(result2["records"]) == 1, "第2页应返回1条记录"


class TestAdminProductTypeExport:
    """测试导出功能的产品类型支持"""

    @pytest.fixture
    def setup_export_data(self, test_db_path):
        """准备导出测试数据"""
        conn = sqlite3.connect(test_db_path)
        cursor = conn.cursor()

        from app.core.timezone import get_beijing_now_naive
        beijing_now = get_beijing_now_naive().isoformat()

        test_records = [
            ("123456", "EX001", "销售", "油脂", "export1.jpg", 1024, ".jpg", "success", "/tmp/export1.jpg"),
            ("123457", "EX002", "销售", "快消", "export2.jpg", 2048, ".jpg", "success", "/tmp/export2.jpg"),
            ("123458", "EX003", "转库", None, "export3.jpg", 3072, ".jpg", "success", "/tmp/export3.jpg"),
        ]

        for record in test_records:
            cursor.execute("""
                INSERT INTO upload_history
                (business_id, doc_number, doc_type, product_type, file_name, file_size,
                 file_extension, upload_time, status, local_file_path, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, record + (beijing_now, beijing_now))

        conn.commit()

        yield conn

        # 清理
        cursor.execute("DELETE FROM upload_history WHERE doc_number LIKE 'EX00%'")
        conn.commit()
        conn.close()

    def test_export_includes_product_type_column(self, setup_export_data):
        """测试导出的Excel包含产品类型列"""
        with patch('app.api.admin.get_db_connection') as mock_db_conn:
            mock_db_conn.return_value = setup_export_data

            response = client.get("/api/admin/export")

            assert response.status_code == 200
            assert response.headers["content-type"] == "application/zip"

            # 注意：实际验证Excel内容需要解压ZIP并读取Excel文件
            # 这里只验证响应成功和content-type正确

    def test_export_with_product_type_filter(self, setup_export_data):
        """测试导出时product_type筛选生效"""
        with patch('app.api.admin.get_db_connection') as mock_db_conn:
            mock_db_conn.return_value = setup_export_data

            # 只导出油脂产品
            response = client.get("/api/admin/export?product_type=油脂")

            assert response.status_code == 200
            assert response.headers["content-type"] == "application/zip"

            # 实际应用中,应该解压ZIP并验证Excel只包含油脂产品

    def test_export_null_product_type_as_empty_string(self, setup_export_data):
        """测试导出时NULL值显示为空字符串"""
        # 这个测试需要实际读取Excel内容,这里作为占位
        # 在实际测试中,应解压ZIP,读取Excel,验证NULL值单元格为空
        pass


class TestAdminRecordsResponseFormat:
    """测试管理接口响应格式"""

    def test_records_response_structure(self, test_db_path):
        """测试响应结构包含所有必要字段"""
        conn = sqlite3.connect(test_db_path)
        cursor = conn.cursor()

        from app.core.timezone import get_beijing_now_naive
        beijing_now = get_beijing_now_naive().isoformat()

        # 插入一条完整记录
        cursor.execute("""
            INSERT INTO upload_history
            (business_id, doc_number, doc_type, product_type, file_name, file_size,
             file_extension, upload_time, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "123456",
            "STRUCT_001",
            "销售",
            "油脂",
            "struct_test.jpg",
            1024,
            ".jpg",
            beijing_now,
            "success",
            beijing_now,
            beijing_now
        ))
        conn.commit()

        with patch('app.api.admin.get_db_connection') as mock_db_conn:
            mock_db_conn.return_value = conn

            response = client.get("/api/admin/records?page=1&page_size=20")

            assert response.status_code == 200
            result = response.json()

            # 验证顶层结构
            assert "total" in result
            assert "page" in result
            assert "page_size" in result
            assert "total_pages" in result
            assert "records" in result

            # 验证记录结构
            if len(result["records"]) > 0:
                record = result["records"][0]
                required_fields = [
                    "id", "business_id", "doc_number", "doc_type",
                    "product_type", "file_name", "file_size",
                    "upload_time", "status"
                ]
                for field in required_fields:
                    assert field in record, f"记录缺少字段: {field}"

        # 清理
        cursor.execute("DELETE FROM upload_history WHERE doc_number = 'STRUCT_001'")
        conn.commit()
        conn.close()
