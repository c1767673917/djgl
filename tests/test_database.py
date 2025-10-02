"""测试数据库操作"""
import pytest
import sqlite3
import os
import tempfile
from unittest.mock import patch, Mock

from app.core.database import get_db_connection, init_database


class TestDatabaseConnection:
    """测试数据库连接"""

    def test_get_db_connection_creates_directory(self):
        """测试数据库连接自动创建目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "subdir", "test.db")

            with patch('app.core.config.get_settings') as mock_settings:
                mock_settings_obj = Mock()
                mock_settings_obj.DATABASE_URL = f"sqlite:///{db_path}"
                mock_settings.return_value = mock_settings_obj

                conn = get_db_connection()
                assert conn is not None

                # 验证目录被创建
                assert os.path.exists(os.path.dirname(db_path))

                conn.close()

    def test_get_db_connection_row_factory(self):
        """测试数据库连接使用Row工厂"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.db', delete=False) as f:
            db_path = f.name

        try:
            with patch('app.core.config.get_settings') as mock_settings:
                mock_settings_obj = Mock()
                mock_settings_obj.DATABASE_URL = f"sqlite:///{db_path}"
                mock_settings.return_value = mock_settings_obj

                conn = get_db_connection()

                # 验证row_factory被设置
                assert conn.row_factory == sqlite3.Row

                conn.close()
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)


class TestDatabaseInitialization:
    """测试数据库初始化"""

    def test_init_database_creates_table(self):
        """测试初始化创建upload_history表"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.db', delete=False) as f:
            db_path = f.name

        try:
            with patch('app.core.config.get_settings') as mock_settings:
                mock_settings_obj = Mock()
                mock_settings_obj.DATABASE_URL = f"sqlite:///{db_path}"
                mock_settings.return_value = mock_settings_obj

                init_database()

                # 验证表被创建
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT name FROM sqlite_master
                    WHERE type='table' AND name='upload_history'
                """)
                result = cursor.fetchone()

                assert result is not None
                assert result[0] == "upload_history"

                conn.close()
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_init_database_table_schema(self):
        """测试表结构包含所有必需字段"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.db', delete=False) as f:
            db_path = f.name

        try:
            with patch('app.core.config.get_settings') as mock_settings:
                mock_settings_obj = Mock()
                mock_settings_obj.DATABASE_URL = f"sqlite:///{db_path}"
                mock_settings.return_value = mock_settings_obj

                init_database()

                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()

                cursor.execute("PRAGMA table_info(upload_history)")
                columns = cursor.fetchall()

                column_names = [col[1] for col in columns]

                # 验证所有必需字段存在
                required_fields = [
                    "id", "business_id", "file_name", "file_size",
                    "file_extension", "upload_time", "status",
                    "error_code", "error_message", "yonyou_file_id",
                    "retry_count", "created_at", "updated_at"
                ]

                for field in required_fields:
                    assert field in column_names, f"Missing field: {field}"

                conn.close()
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_init_database_creates_indexes(self):
        """测试初始化创建索引"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.db', delete=False) as f:
            db_path = f.name

        try:
            with patch('app.core.config.get_settings') as mock_settings:
                mock_settings_obj = Mock()
                mock_settings_obj.DATABASE_URL = f"sqlite:///{db_path}"
                mock_settings.return_value = mock_settings_obj

                init_database()

                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT name FROM sqlite_master
                    WHERE type='index'
                """)
                indexes = cursor.fetchall()
                index_names = [idx[0] for idx in indexes]

                # 验证必需的索引
                assert "idx_business_id" in index_names
                assert "idx_upload_time" in index_names
                assert "idx_status" in index_names

                conn.close()
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_init_database_idempotent(self):
        """测试重复初始化不会出错(IF NOT EXISTS)"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.db', delete=False) as f:
            db_path = f.name

        try:
            with patch('app.core.config.get_settings') as mock_settings:
                mock_settings_obj = Mock()
                mock_settings_obj.DATABASE_URL = f"sqlite:///{db_path}"
                mock_settings.return_value = mock_settings_obj

                # 第一次初始化
                init_database()

                # 第二次初始化(不应该出错)
                init_database()

                # 验证表仍然存在且正常
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT name FROM sqlite_master
                    WHERE type='table' AND name='upload_history'
                """)
                result = cursor.fetchone()

                assert result is not None

                conn.close()
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)


class TestDatabaseOperations:
    """测试数据库CRUD操作"""

    def test_insert_upload_record(self, test_db_path):
        """测试插入上传记录"""
        conn = sqlite3.connect(test_db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO upload_history
            (business_id, file_name, file_size, file_extension, status,
             error_code, error_message, yonyou_file_id, retry_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ("123456", "test.jpg", 1024, ".jpg", "success", None, None, "file_id_123", 0))

        conn.commit()

        # 验证插入成功
        cursor.execute("SELECT * FROM upload_history WHERE business_id = ?", ("123456",))
        record = cursor.fetchone()

        assert record is not None
        assert record[1] == "123456"  # business_id
        assert record[2] == "test.jpg"  # file_name
        assert record[3] == 1024  # file_size

        conn.close()

    def test_query_by_business_id(self, test_db_path):
        """测试按business_id查询记录"""
        conn = sqlite3.connect(test_db_path)
        cursor = conn.cursor()

        # 插入多条记录
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

        # 查询特定business_id
        cursor.execute("""
            SELECT * FROM upload_history
            WHERE business_id = ?
        """, ("123456",))

        records = cursor.fetchall()

        assert len(records) == 2
        assert all(r[1] == "123456" for r in records)

        conn.close()

    def test_index_performance(self, test_db_path):
        """测试索引提升查询性能"""
        conn = sqlite3.connect(test_db_path)
        cursor = conn.cursor()

        # 插入大量测试数据
        test_data = [
            (f"{i:06d}", f"test{i}.jpg", 1024, ".jpg", "success", None, None, f"file_id_{i}", 0)
            for i in range(1000)
        ]

        cursor.executemany("""
            INSERT INTO upload_history
            (business_id, file_name, file_size, file_extension, status,
             error_code, error_message, yonyou_file_id, retry_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, test_data)

        conn.commit()

        # 验证索引被使用(通过EXPLAIN QUERY PLAN)
        cursor.execute("""
            EXPLAIN QUERY PLAN
            SELECT * FROM upload_history WHERE business_id = ?
        """, ("000500",))

        plan = cursor.fetchall()
        plan_str = str(plan)

        # 应该使用索引扫描而不是全表扫描
        assert "idx_business_id" in plan_str or "SEARCH" in plan_str

        conn.close()

    def test_default_timestamps(self, test_db_path):
        """测试默认时间戳字段"""
        conn = sqlite3.connect(test_db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO upload_history
            (business_id, file_name, file_size, file_extension, status,
             error_code, error_message, yonyou_file_id, retry_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ("123456", "test.jpg", 1024, ".jpg", "success", None, None, "file_id_123", 0))

        conn.commit()

        cursor.execute("SELECT upload_time, created_at, updated_at FROM upload_history WHERE business_id = ?", ("123456",))
        record = cursor.fetchone()

        # 验证时间戳字段不为空
        assert record[0] is not None  # upload_time
        assert record[1] is not None  # created_at
        assert record[2] is not None  # updated_at

        conn.close()

    def test_null_handling(self, test_db_path):
        """测试NULL值处理"""
        conn = sqlite3.connect(test_db_path)
        cursor = conn.cursor()

        # 插入包含NULL的记录
        cursor.execute("""
            INSERT INTO upload_history
            (business_id, file_name, file_size, file_extension, status,
             error_code, error_message, yonyou_file_id, retry_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ("123456", "test.jpg", 1024, ".jpg", "failed", "40000", None, None, 2))

        conn.commit()

        cursor.execute("SELECT * FROM upload_history WHERE business_id = ?", ("123456",))
        record = cursor.fetchone()

        # 验证NULL值正确存储
        assert record[8] is None  # error_message
        assert record[9] is None  # yonyou_file_id

        conn.close()
