import sqlite3
import os
from app.core.config import get_settings

settings = get_settings()


def get_db_connection():
    """获取数据库连接"""
    db_path = settings.DATABASE_URL.replace("sqlite:///", "")
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    """初始化数据库"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # 创建上传历史表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS upload_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id VARCHAR(50) NOT NULL,
            file_name VARCHAR(255) NOT NULL,
            file_size INTEGER NOT NULL,
            file_extension VARCHAR(20),
            upload_time DATETIME DEFAULT CURRENT_TIMESTAMP,
            status VARCHAR(20) NOT NULL,
            error_code VARCHAR(50),
            error_message TEXT,
            yonyou_file_id VARCHAR(255),
            retry_count INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

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

    conn.commit()
    conn.close()
