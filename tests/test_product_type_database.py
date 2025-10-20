"""测试产品类型数据库变更"""
import pytest
import sqlite3
from app.core.database import init_database, get_db_connection


class TestProductTypeDatabaseMigration:
    """测试产品类型字段和索引的数据库迁移"""

    def test_product_type_field_exists(self):
        """测试product_type字段已创建"""
        conn = get_db_connection()
        cursor = conn.cursor()

        # 查询表结构
        cursor.execute("PRAGMA table_info(upload_history)")
        columns = [column[1] for column in cursor.fetchall()]

        # 验证product_type字段存在
        assert 'product_type' in columns, "product_type字段未创建"

        conn.close()

    def test_product_type_field_type(self):
        """测试product_type字段类型为TEXT"""
        conn = get_db_connection()
        cursor = conn.cursor()

        # 查询字段详细信息
        cursor.execute("PRAGMA table_info(upload_history)")
        columns = {col[1]: col for col in cursor.fetchall()}

        # 验证字段存在且类型正确
        assert 'product_type' in columns, "product_type字段不存在"

        product_type_col = columns['product_type']
        col_type = product_type_col[2]  # 索引2是type
        col_notnull = product_type_col[3]  # 索引3是notnull
        col_default = product_type_col[4]  # 索引4是dflt_value

        # 验证类型为TEXT
        assert col_type == 'TEXT', f"product_type字段类型应为TEXT,实际为{col_type}"

        # 验证允许NULL (notnull=0表示允许NULL)
        assert col_notnull == 0, f"product_type字段应允许NULL,实际notnull={col_notnull}"

        # 验证默认值为NULL
        assert col_default is None, f"product_type默认值应为NULL,实际为{col_default}"

        conn.close()

    def test_product_type_index_exists(self):
        """测试idx_product_type索引已创建"""
        conn = get_db_connection()
        cursor = conn.cursor()

        # 查询索引
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='index' AND name='idx_product_type'
        """)
        result = cursor.fetchone()

        # 验证索引存在
        assert result is not None, "idx_product_type索引未创建"
        assert result[0] == 'idx_product_type', "索引名称不匹配"

        conn.close()

    def test_product_type_index_on_correct_column(self):
        """测试索引是否在正确的列上"""
        conn = get_db_connection()
        cursor = conn.cursor()

        # 查询索引信息
        cursor.execute("PRAGMA index_info(idx_product_type)")
        index_columns = cursor.fetchall()

        # 验证索引列
        assert len(index_columns) > 0, "索引没有列信息"
        assert index_columns[0][2] == 'product_type', "索引应建立在product_type列上"

        conn.close()

    def test_existing_records_have_null_product_type(self):
        """测试现有记录的product_type字段为NULL（向后兼容）"""
        conn = get_db_connection()
        cursor = conn.cursor()

        # 插入测试数据（模拟旧数据，不包含product_type）
        from app.core.timezone import get_beijing_now_naive
        beijing_now = get_beijing_now_naive().isoformat()

        cursor.execute("""
            INSERT INTO upload_history
            (business_id, doc_number, doc_type, file_name, file_size, file_extension,
             upload_time, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "123456",
            "TEST_NULL_PT",
            "销售",
            "test_null.jpg",
            1024,
            ".jpg",
            beijing_now,
            "success",
            beijing_now,
            beijing_now
        ))

        # 查询刚插入的记录
        cursor.execute("""
            SELECT product_type FROM upload_history
            WHERE doc_number = 'TEST_NULL_PT'
        """)
        result = cursor.fetchone()

        # 验证product_type为NULL
        assert result is not None, "测试记录未插入"
        assert result[0] is None, "旧记录的product_type应为NULL"

        # 清理测试数据
        cursor.execute("DELETE FROM upload_history WHERE doc_number = 'TEST_NULL_PT'")
        conn.commit()
        conn.close()

    def test_database_migration_idempotent(self):
        """测试数据库迁移是幂等的（可重复执行）"""
        # 第一次初始化
        init_database()

        # 第二次初始化（应该不报错）
        try:
            init_database()
        except Exception as e:
            pytest.fail(f"数据库迁移不是幂等的，重复执行报错: {str(e)}")

        # 验证字段和索引仍然存在
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("PRAGMA table_info(upload_history)")
        columns = [column[1] for column in cursor.fetchall()]
        assert 'product_type' in columns, "重复迁移后product_type字段丢失"

        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='index' AND name='idx_product_type'
        """)
        result = cursor.fetchone()
        assert result is not None, "重复迁移后idx_product_type索引丢失"

        conn.close()

    def test_product_type_allows_arbitrary_values(self):
        """测试product_type字段允许任意字符串值（不限于预设值）"""
        conn = get_db_connection()
        cursor = conn.cursor()

        from app.core.timezone import get_beijing_now_naive
        beijing_now = get_beijing_now_naive().isoformat()

        # 测试各种值
        test_values = [
            "油脂",
            "快消",
            "调味品",
            "日化用品",
            "特殊字符@#$%",
            "very_long_string_" * 10,  # 超长字符串
            "",  # 空字符串
            None  # NULL
        ]

        for idx, test_value in enumerate(test_values):
            doc_number = f"TEST_PT_{idx}"

            cursor.execute("""
                INSERT INTO upload_history
                (business_id, doc_number, doc_type, product_type, file_name, file_size,
                 file_extension, upload_time, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                "123456",
                doc_number,
                "销售",
                test_value,
                f"test_{idx}.jpg",
                1024,
                ".jpg",
                beijing_now,
                "success",
                beijing_now,
                beijing_now
            ))

            # 验证存储的值
            cursor.execute("""
                SELECT product_type FROM upload_history
                WHERE doc_number = ?
            """, (doc_number,))
            result = cursor.fetchone()

            assert result is not None, f"测试记录{doc_number}未插入"
            assert result[0] == test_value, f"product_type值不匹配: 期望{test_value}, 实际{result[0]}"

        # 清理测试数据
        for idx in range(len(test_values)):
            cursor.execute("DELETE FROM upload_history WHERE doc_number = ?", (f"TEST_PT_{idx}",))

        conn.commit()
        conn.close()
