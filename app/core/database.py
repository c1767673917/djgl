import sqlite3
import os
import asyncio
import threading
from contextlib import contextmanager
from app.core.config import get_settings

settings = get_settings()

# 全局数据库锁，确保并发安全
db_lock = threading.RLock()


@contextmanager
def get_db_connection():
    """获取数据库连接的上下文管理器，确保并发安全"""
    conn = None
    try:
        db_path = settings.DATABASE_URL.replace("sqlite:///", "")
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

        with db_lock:  # 使用线程锁确保并发安全
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            # 启用WAL模式以支持更好的并发读取
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('PRAGMA synchronous=NORMAL')
            conn.execute('PRAGMA cache_size=1000')
            conn.execute('PRAGMA temp_store=MEMORY')
            yield conn
    except Exception as e:
        if conn:
            conn.rollback()
        raise e
    finally:
        if conn:
            conn.close()


def get_db_connection_simple():
    """获取简单的数据库连接（向后兼容）"""
    db_path = settings.DATABASE_URL.replace("sqlite:///", "")
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    """初始化数据库"""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # 创建上传历史表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS upload_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                business_id VARCHAR(50) NOT NULL,
                doc_number VARCHAR(100),
                doc_type VARCHAR(20),
                file_name VARCHAR(255) NOT NULL,
                file_size INTEGER NOT NULL,
                file_extension VARCHAR(20),
                upload_time DATETIME,
                status VARCHAR(20) NOT NULL,
                error_code VARCHAR(50),
                error_message TEXT,
                yonyou_file_id VARCHAR(255),
                retry_count INTEGER DEFAULT 0,
                local_file_path VARCHAR(500),
                created_at DATETIME,
                updated_at DATETIME
            )
        """)

        # 检查并新增字段（兼容现有数据库）
        cursor.execute("PRAGMA table_info(upload_history)")
        columns = [column[1] for column in cursor.fetchall()]

        if 'doc_number' not in columns:
            cursor.execute("ALTER TABLE upload_history ADD COLUMN doc_number VARCHAR(100)")

        if 'doc_type' not in columns:
            cursor.execute("ALTER TABLE upload_history ADD COLUMN doc_type VARCHAR(20)")

        if 'local_file_path' not in columns:
            cursor.execute("ALTER TABLE upload_history ADD COLUMN local_file_path VARCHAR(500)")

        if 'deleted_at' not in columns:
            cursor.execute("ALTER TABLE upload_history ADD COLUMN deleted_at TEXT DEFAULT NULL")

        # 添加产品类型字段 (支持产品维度分类管理)
        if 'product_type' not in columns:
            cursor.execute("ALTER TABLE upload_history ADD COLUMN product_type TEXT DEFAULT NULL")

        # 添加检查状态字段 (支持质量检查工作流)
        if 'checked' not in columns:
            cursor.execute("ALTER TABLE upload_history ADD COLUMN checked INTEGER DEFAULT 0")

        # 添加备注字段 (支持管理员手工填入备注文本)
        if 'notes' not in columns:
            cursor.execute("ALTER TABLE upload_history ADD COLUMN notes TEXT DEFAULT NULL")

        # 创建索引
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_business_id
            ON upload_history(business_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_upload_time
            ON upload_history(upload_time)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_status
            ON upload_history(status)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_doc_number
            ON upload_history(doc_number)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_doc_type
            ON upload_history(doc_type)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_doc_type_upload_time
            ON upload_history(doc_type, upload_time)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_deleted_at
            ON upload_history(deleted_at)
        """)

        # 产品类型索引 (优化产品类型筛选查询性能)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_product_type
            ON upload_history(product_type)
        """)

        # 检查状态索引 (优化检查状态筛选查询性能)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_checked
            ON upload_history(checked)
        """)

        conn.commit()
