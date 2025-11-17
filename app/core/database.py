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
                logistics TEXT,
                created_at DATETIME,
                updated_at DATETIME,
                deleted_at DATETIME
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
            cursor.execute("ALTER TABLE upload_history ADD COLUMN deleted_at DATETIME DEFAULT NULL")

        # 添加产品类型字段 (支持产品维度分类管理)
        if 'product_type' not in columns:
            cursor.execute("ALTER TABLE upload_history ADD COLUMN product_type TEXT DEFAULT NULL")

        # 添加检查状态字段 (支持质量检查工作流)
        if 'checked' not in columns:
            cursor.execute("ALTER TABLE upload_history ADD COLUMN checked INTEGER DEFAULT 0")

        # 添加备注字段 (支持管理员手工填入备注文本)
        if 'notes' not in columns:
            cursor.execute("ALTER TABLE upload_history ADD COLUMN notes TEXT DEFAULT NULL")

        # 添加物流字段 (支持物流公司筛选)
        if 'logistics' not in columns:
            cursor.execute("ALTER TABLE upload_history ADD COLUMN logistics TEXT DEFAULT NULL")

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

        # 物流字段索引 (优化物流筛选查询性能)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_logistics
            ON upload_history(logistics)
        """)

        conn.commit()


def verify_database_schema():
    """
    验证数据库schema是否包含WebDAV支持所需的必需字段

    这个函数会在应用启动时被调用,确保数据库具备正确的表结构。
    如果缺少必需字段,会抛出RuntimeError并提供修复建议。

    Raises:
        RuntimeError: 当数据库缺少必需字段时
    """
    import logging
    logger = logging.getLogger(__name__)

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            # 获取upload_history表的所有列
            cursor.execute("PRAGMA table_info(upload_history)")
            columns = {col[1] for col in cursor.fetchall()}

            # 定义必需的WebDAV相关字段
            required_fields = {
                'webdav_path': 'WebDAV远程文件路径',
                'is_cached': '是否已缓存标志',
                'cache_expiry_time': '缓存过期时间'
            }

            # 检查缺失的字段
            missing_fields = [
                (field, desc)
                for field, desc in required_fields.items()
                if field not in columns
            ]

            if missing_fields:
                missing_list = '\n'.join([f"  - {field}: {desc}" for field, desc in missing_fields])
                error_msg = (
                    f"\n{'='*60}\n"
                    f"数据库Schema验证失败!\n"
                    f"{'='*60}\n"
                    f"upload_history表缺少以下必需字段:\n"
                    f"{missing_list}\n\n"
                    f"修复方法:\n"
                    f"1. 如果有迁移脚本,请执行:\n"
                    f"   sqlite3 data/uploads.db < migrations/add_webdav_support.sql\n\n"
                    f"2. 或者手动添加字段:\n"
                    f"   ALTER TABLE upload_history ADD COLUMN webdav_path TEXT;\n"
                    f"   ALTER TABLE upload_history ADD COLUMN is_cached BOOLEAN DEFAULT 1;\n"
                    f"   ALTER TABLE upload_history ADD COLUMN cache_expiry_time DATETIME;\n"
                    f"{'='*60}\n"
                )
                logger.error(error_msg)
                raise RuntimeError(error_msg)

            logger.info(f"数据库Schema验证通过 - 所有必需字段都存在 ({len(required_fields)}个)")

            # 统计现有数据
            cursor.execute("SELECT COUNT(*) FROM upload_history")
            total_records = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM upload_history WHERE webdav_path IS NOT NULL AND webdav_path != ''")
            webdav_records = cursor.fetchone()[0]

            logger.info(f"数据库统计: 总记录数={total_records}, WebDAV记录数={webdav_records}")

    except RuntimeError:
        # 重新抛出schema验证错误
        raise
    except Exception as e:
        error_msg = f"数据库Schema验证过程中出错: {str(e)}"
        logger.error(error_msg)
        raise RuntimeError(error_msg)
