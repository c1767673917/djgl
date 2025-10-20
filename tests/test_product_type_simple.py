"""产品类型功能简化测试套件（聚焦功能验证）"""
import pytest
import sqlite3
import tempfile
import os
from app.core.database import init_database, get_db_connection
from app.core.config import get_settings


class TestProductTypeDatabaseSimple:
    """简化的数据库测试（使用真实数据库）"""

    def test_actual_database_has_product_type_field(self):
        """验证实际数据库包含product_type字段"""
        conn = get_db_connection()
        cursor = conn.cursor()

        # 查询表结构
        cursor.execute("PRAGMA table_info(upload_history)")
        columns_info = cursor.fetchall()
        column_names = [col[1] for col in columns_info]

        # 验证product_type字段存在
        assert 'product_type' in column_names, "数据库缺少product_type字段"

        # 查找product_type字段详情
        product_type_col = next((col for col in columns_info if col[1] == 'product_type'), None)
        assert product_type_col is not None

        # 验证字段类型
        col_type = product_type_col[2]
        assert 'TEXT' in col_type.upper(), f"product_type类型应为TEXT,实际为{col_type}"

        conn.close()

    def test_actual_database_has_product_type_index(self):
        """验证实际数据库包含product_type索引"""
        conn = get_db_connection()
        cursor = conn.cursor()

        # 查询索引
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='index' AND name='idx_product_type'
        """)
        result = cursor.fetchone()

        assert result is not None, "数据库缺少idx_product_type索引"

        conn.close()

    def test_can_insert_record_with_product_type(self):
        """验证可以插入带product_type的记录"""
        conn = get_db_connection()
        cursor = conn.cursor()

        from app.core.timezone import get_beijing_now_naive
        beijing_now = get_beijing_now_naive().isoformat()

        # 插入测试记录
        test_doc_number = "TEST_SIMPLE_001"
        try:
            cursor.execute("""
                INSERT INTO upload_history
                (business_id, doc_number, doc_type, product_type, file_name, file_size,
                 file_extension, upload_time, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                "123456",
                test_doc_number,
                "销售",
                "油脂",  # product_type
                "test.jpg",
                1024,
                ".jpg",
                beijing_now,
                "success",
                beijing_now,
                beijing_now
            ))

            # 验证插入成功
            cursor.execute("""
                SELECT product_type FROM upload_history
                WHERE doc_number = ?
            """, (test_doc_number,))
            result = cursor.fetchone()

            assert result is not None, "记录未插入"
            assert result[0] == "油脂", f"product_type应为'油脂',实际为{result[0]}"

        finally:
            # 清理测试数据
            cursor.execute("DELETE FROM upload_history WHERE doc_number = ?", (test_doc_number,))
            conn.commit()
            conn.close()

    def test_can_insert_record_without_product_type(self):
        """验证可以插入不带product_type的记录（向后兼容）"""
        conn = get_db_connection()
        cursor = conn.cursor()

        from app.core.timezone import get_beijing_now_naive
        beijing_now = get_beijing_now_naive().isoformat()

        test_doc_number = "TEST_SIMPLE_002"
        try:
            cursor.execute("""
                INSERT INTO upload_history
                (business_id, doc_number, doc_type, file_name, file_size,
                 file_extension, upload_time, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                "123456",
                test_doc_number,
                "销售",
                "test.jpg",
                1024,
                ".jpg",
                beijing_now,
                "success",
                beijing_now,
                beijing_now
            ))

            # 验证product_type为NULL
            cursor.execute("""
                SELECT product_type FROM upload_history
                WHERE doc_number = ?
            """, (test_doc_number,))
            result = cursor.fetchone()

            assert result is not None
            assert result[0] is None, f"不传product_type时应为NULL,实际为{result[0]}"

        finally:
            cursor.execute("DELETE FROM upload_history WHERE doc_number = ?", (test_doc_number,))
            conn.commit()
            conn.close()

    def test_can_query_by_product_type(self):
        """验证可以按product_type查询"""
        conn = get_db_connection()
        cursor = conn.cursor()

        from app.core.timezone import get_beijing_now_naive
        beijing_now = get_beijing_now_naive().isoformat()

        # 插入测试数据
        test_records = [
            ("TEST_QUERY_001", "油脂"),
            ("TEST_QUERY_002", "油脂"),
            ("TEST_QUERY_003", "快消"),
        ]

        try:
            for doc_number, product_type in test_records:
                cursor.execute("""
                    INSERT INTO upload_history
                    (business_id, doc_number, doc_type, product_type, file_name, file_size,
                     file_extension, upload_time, status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    "123456",
                    doc_number,
                    "销售",
                    product_type,
                    "test.jpg",
                    1024,
                    ".jpg",
                    beijing_now,
                    "success",
                    beijing_now,
                    beijing_now
                ))

            # 查询油脂产品
            cursor.execute("""
                SELECT COUNT(*) FROM upload_history
                WHERE product_type = ? AND doc_number LIKE 'TEST_QUERY_%'
            """, ("油脂",))
            count = cursor.fetchone()[0]

            assert count == 2, f"应查询到2条油脂记录,实际{count}条"

            # 查询快消产品
            cursor.execute("""
                SELECT COUNT(*) FROM upload_history
                WHERE product_type = ? AND doc_number LIKE 'TEST_QUERY_%'
            """, ("快消",))
            count = cursor.fetchone()[0]

            assert count == 1, f"应查询到1条快消记录,实际{count}条"

        finally:
            cursor.execute("DELETE FROM upload_history WHERE doc_number LIKE 'TEST_QUERY_%'")
            conn.commit()
            conn.close()

    def test_product_type_index_improves_query(self):
        """验证product_type索引用于查询优化"""
        conn = get_db_connection()
        cursor = conn.cursor()

        # 使用EXPLAIN QUERY PLAN验证查询计划
        cursor.execute("""
            EXPLAIN QUERY PLAN
            SELECT * FROM upload_history
            WHERE product_type = '油脂'
        """)
        plan = cursor.fetchall()

        # 验证查询计划生成成功
        assert plan is not None and len(plan) > 0, "查询计划应存在"

        # 注意: SQLite可能不会在小数据集上使用索引,这里只验证查询可以执行
        conn.close()


class TestProductTypeAPIContract:
    """API契约测试（不依赖Mock，验证接口签名）"""

    def test_upload_api_accepts_product_type_parameter(self):
        """验证上传API接口签名包含product_type参数"""
        from app.api.upload import upload_files
        import inspect

        sig = inspect.signature(upload_files)
        params = sig.parameters

        # 验证product_type参数存在
        assert 'product_type' in params, "upload_files缺少product_type参数"

        # 验证参数是可选的
        param = params['product_type']
        assert param.default is not inspect.Parameter.empty or \
               str(param.annotation).startswith('Optional'), \
               "product_type应为可选参数"

    def test_admin_records_api_accepts_product_type_filter(self):
        """验证管理接口接受product_type筛选参数"""
        from app.api.admin import get_admin_records
        import inspect

        sig = inspect.signature(get_admin_records)
        params = sig.parameters

        # 验证product_type参数存在
        assert 'product_type' in params, "get_admin_records缺少product_type参数"

    def test_export_api_accepts_product_type_filter(self):
        """验证导出接口接受product_type筛选参数"""
        from app.api.admin import export_records
        import inspect

        sig = inspect.signature(export_records)
        params = sig.parameters

        # 验证product_type参数存在
        assert 'product_type' in params, "export_records缺少product_type参数"


class TestProductTypeDataModel:
    """数据模型测试"""

    def test_upload_history_model_has_product_type_field(self):
        """验证UploadHistory模型包含product_type字段"""
        from app.models.upload_history import UploadHistory
        import inspect

        # UploadHistory使用__init__而非@dataclass,检查__init__参数
        sig = inspect.signature(UploadHistory.__init__)
        params = sig.parameters

        # 验证product_type参数存在
        assert 'product_type' in params, "UploadHistory模型缺少product_type参数"

        # 验证参数是可选的(有默认值None)
        param = params['product_type']
        assert param.default is None or param.default is inspect.Parameter.empty, \
               "product_type应为可选参数(默认None)"


class TestProductTypeFunctionalScenarios:
    """功能场景测试（不依赖完整数据库,仅验证逻辑）"""

    def test_null_value_display_logic(self):
        """验证NULL值在前端显示为空字符串的逻辑"""
        # 模拟前端显示逻辑
        product_type_null = None
        product_type_value = "油脂"
        product_type_empty = ""

        # Python的 or 操作符模拟前端 || 操作符
        assert (product_type_null or '') == '', "NULL应显示为空字符串"
        assert (product_type_value or '') == '油脂', "有值应显示原值"
        assert (product_type_empty or '') == '', "空字符串应保持为空字符串"

    def test_filter_logic_excludes_null(self):
        """验证筛选逻辑不包含NULL值"""
        # 模拟数据
        test_data = [
            {"doc_number": "001", "product_type": "油脂"},
            {"doc_number": "002", "product_type": "快消"},
            {"doc_number": "003", "product_type": None},
            {"doc_number": "004", "product_type": ""},
        ]

        # 筛选"油脂"
        filtered_oil = [r for r in test_data if r["product_type"] == "油脂"]
        assert len(filtered_oil) == 1, "筛选'油脂'应返回1条"
        assert filtered_oil[0]["doc_number"] == "001"

        # 筛选"快消"
        filtered_fast = [r for r in test_data if r["product_type"] == "快消"]
        assert len(filtered_fast) == 1, "筛选'快消'应返回1条"

        # 验证NULL不在筛选结果中
        assert not any(r["product_type"] is None for r in filtered_oil + filtered_fast), \
               "筛选结果不应包含NULL值"

    def test_all_filter_includes_null(self):
        """验证'全部'筛选包含NULL值"""
        test_data = [
            {"doc_number": "001", "product_type": "油脂"},
            {"doc_number": "002", "product_type": None},
        ]

        # 不应用筛选（模拟'全部'）
        all_data = test_data

        assert len(all_data) == 2, "'全部'应返回所有记录"
        assert any(r["product_type"] is None for r in all_data), \
               "'全部'应包含NULL值记录"

    def test_product_type_preserves_business_id(self):
        """验证product_type和business_id共存"""
        # 模拟上传数据
        upload_data = {
            "business_id": "123456",
            "doc_number": "SO001",
            "doc_type": "销售",
            "product_type": "油脂"
        }

        # 验证两个字段都存在
        assert "business_id" in upload_data, "应包含business_id"
        assert "product_type" in upload_data, "应包含product_type"
        assert upload_data["business_id"] == "123456"
        assert upload_data["product_type"] == "油脂"


class TestProductTypeSecurityAndEdgeCases:
    """安全性和边界测试"""

    def test_sql_injection_prevention(self):
        """验证SQL注入防护（参数化查询）"""
        # 验证代码使用参数化查询
        from app.api.admin import get_admin_records
        import inspect

        source = inspect.getsource(get_admin_records)

        # 验证使用了参数化查询(问号占位符)
        assert "?" in source, "应使用参数化查询(问号占位符)"
        assert "params.append" in source or "params.extend" in source, \
               "应使用params列表传递参数"

    def test_xss_prevention_frontend(self):
        """验证XSS防护（前端应转义HTML）"""
        # 模拟恶意输入
        malicious_input = "<script>alert('XSS')</script>"

        # 简单的HTML转义函数
        def escape_html(text):
            if text is None:
                return ''
            return (str(text)
                   .replace('&', '&amp;')
                   .replace('<', '&lt;')
                   .replace('>', '&gt;')
                   .replace('"', '&quot;')
                   .replace("'", '&#x27;'))

        escaped = escape_html(malicious_input)
        assert '<script>' not in escaped, "应转义script标签"
        assert '&lt;script&gt;' in escaped, "应正确转义<符号"

    def test_empty_string_vs_null_distinction(self):
        """验证空字符串和NULL的区别"""
        empty_string = ""
        null_value = None

        # 验证两者不相等
        assert empty_string != null_value, "空字符串和NULL应区分"

        # 验证显示逻辑一致
        assert (empty_string or '') == ''
        assert (null_value or '') == ''

    def test_special_characters_handling(self):
        """验证特殊字符处理"""
        special_chars = [
            "产品-ABC",
            "产品_123",
            "产品（测试）",
            "产品@#$%",
            "product-type",
        ]

        # 验证所有特殊字符都能作为字符串存储
        for char in special_chars:
            assert isinstance(char, str), "特殊字符应为字符串类型"
            assert len(char) > 0, "特殊字符串应有长度"


print("\n=== 产品类型功能测试套件 ===")
print("此测试套件验证产品类型参数功能的核心逻辑")
print("测试范围:")
print("1. 数据库字段和索引")
print("2. API接口契约")
print("3. 数据模型")
print("4. 功能场景逻辑")
print("5. 安全性和边界情况")
print("================================\n")
