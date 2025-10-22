"""Pytest配置文件和共享fixtures"""
import pytest
import asyncio
import os
import tempfile
import sqlite3
from io import BytesIO
from PIL import Image
from typing import Generator


@pytest.fixture(scope="session")
def event_loop():
    """创建事件循环用于异步测试"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def test_db_path() -> Generator[str, None, None]:
    """创建临时测试数据库"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.db', delete=False) as f:
        db_path = f.name

    # 初始化测试数据库
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS upload_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id VARCHAR(50) NOT NULL,
            doc_number VARCHAR(100),
            doc_type VARCHAR(20),
            product_type TEXT DEFAULT NULL,
            file_name VARCHAR(255) NOT NULL,
            file_size INTEGER NOT NULL,
            file_extension VARCHAR(20),
            upload_time DATETIME DEFAULT CURRENT_TIMESTAMP,
            status VARCHAR(20) NOT NULL,
            error_code VARCHAR(50),
            error_message TEXT,
            yonyou_file_id VARCHAR(255),
            retry_count INTEGER DEFAULT 0,
            local_file_path VARCHAR(500),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            deleted_at TEXT DEFAULT NULL,
            checked INTEGER DEFAULT 0,
            notes TEXT DEFAULT NULL
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_business_id
        ON upload_history(business_id)
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
        CREATE INDEX IF NOT EXISTS idx_product_type
        ON upload_history(product_type)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_deleted_at
        ON upload_history(deleted_at)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_checked
        ON upload_history(checked)
    """)

    # notes字段暂不添加索引（不用于查询筛选）
    # 如果未来需要按备注搜索，可添加全文索引

    conn.commit()
    conn.close()

    yield db_path

    # 清理
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture
def test_image_file() -> BytesIO:
    """创建测试图片文件(JPEG格式)"""
    img = Image.new('RGB', (100, 100), color='red')
    img_bytes = BytesIO()
    img.save(img_bytes, format='JPEG')
    img_bytes.seek(0)
    return img_bytes


@pytest.fixture
def test_image_bytes() -> bytes:
    """创建测试图片字节数据"""
    img = Image.new('RGB', (100, 100), color='blue')
    img_bytes = BytesIO()
    img.save(img_bytes, format='JPEG')
    return img_bytes.getvalue()


@pytest.fixture
def large_image_bytes() -> bytes:
    """创建超过10MB的大图片"""
    # 创建一个大尺寸图片
    img = Image.new('RGB', (5000, 5000), color='green')
    img_bytes = BytesIO()
    img.save(img_bytes, format='JPEG', quality=100)
    return img_bytes.getvalue()


@pytest.fixture
def mock_token_response_success():
    """Mock成功的Token响应"""
    return {
        "code": "00000",
        "message": "成功",
        "data": {
            "access_token": "test_access_token_12345",
            "expires_in": 3600
        }
    }


@pytest.fixture
def mock_token_response_error():
    """Mock失败的Token响应"""
    return {
        "code": "50000",
        "message": "认证失败",
        "data": None
    }


@pytest.fixture
def mock_upload_response_success():
    """Mock成功的上传响应"""
    return {
        "code": "200",
        "message": "成功",
        "data": {
            "data": [
                {
                    "id": "file_id_12345",
                    "fileName": "test.jpg",
                    "fileSize": 1024,
                    "fileExtension": ".jpg"
                }
            ]
        }
    }


@pytest.fixture
def mock_upload_response_token_expired_string():
    """Mock Token过期响应(字符串错误码)"""
    return {
        "code": "1090003500065",  # 字符串类型
        "message": "Token已过期",
        "data": None
    }


@pytest.fixture
def mock_upload_response_token_expired_integer():
    """Mock Token过期响应(整数错误码)"""
    return {
        "code": 1090003500065,  # 整数类型
        "message": "Token已过期",
        "data": None
    }


@pytest.fixture
def mock_upload_response_invalid_token():
    """Mock 非法Token响应(错误码310036)"""
    return {
        "code": "310036",
        "message": "非法token",
        "data": None
    }


@pytest.fixture
def mock_upload_response_error():
    """Mock失败的上传响应"""
    return {
        "code": "40000",
        "message": "上传失败",
        "data": None
    }


@pytest.fixture
def mock_token_response_signature_error():
    """Mock签名错误的Token响应"""
    return {
        "code": "50000",
        "message": "签名不正确",
        "data": None
    }


@pytest.fixture
def mock_token_response_signature_error_message():
    """Mock签名错误的Token响应（通过错误信息识别）"""
    return {
        "code": "99999",
        "message": "signature is invalid",
        "data": None
    }


@pytest.fixture
def valid_business_ids():
    """有效的businessId列表"""
    return ["123456", "000000", "999999", "100000"]


@pytest.fixture
def invalid_business_ids():
    """无效的businessId列表"""
    return [
        ("abc", "包含非数字字符"),
        ("12345", "长度不足6位"),
        ("1234567", "长度超过6位"),
        ("", "空字符串"),
        ("12 345", "包含空格"),
    ]
