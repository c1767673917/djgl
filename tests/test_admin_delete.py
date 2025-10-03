"""测试后台管理删除功能

本测试文件专注于验证删除功能的以下核心方面：
1. 软删除策略验证
2. 查询过滤验证
3. 幂等性验证
4. 本地文件保留验证
5. 边界条件测试
"""
import pytest
import sqlite3
import os
import tempfile
import json
from datetime import datetime
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app
from app.core.database import get_db_connection


# ============================================================================
# 测试装置 (Fixtures)
# ============================================================================

@pytest.fixture
def test_client():
    """创建FastAPI测试客户端"""
    return TestClient(app)


def delete_records(client, ids):
    """辅助函数：发送DELETE请求删除记录"""
    return client.request(
        method="DELETE",
        url="/api/admin/records",
        content=json.dumps({"ids": ids}),
        headers={"Content-Type": "application/json"}
    )


def create_mock_db_factory(db_path):
    """辅助函数：创建返回测试数据库连接的工厂函数"""
    def get_test_db():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn
    return get_test_db


@pytest.fixture
def test_db():
    """创建测试数据库并插入测试数据"""
    # 创建临时数据库文件
    with tempfile.NamedTemporaryFile(mode='w', suffix='.db', delete=False) as f:
        db_path = f.name

    # 初始化数据库表结构
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS upload_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id VARCHAR(50) NOT NULL,
            doc_number VARCHAR(100),
            doc_type VARCHAR(20),
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
            deleted_at TEXT DEFAULT NULL
        )
    """)

    # 创建索引
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_deleted_at
        ON upload_history(deleted_at)
    """)

    # 插入测试数据
    test_records = [
        (1, '123456', 'SO20250101001', '销售', 'image1.jpg', 1024, '.jpg',
         '2025-01-01 10:00:00', 'success', None, None, 'file_id_001', 0, '/uploads/image1.jpg', None),
        (2, '123457', 'SO20250101002', '销售', 'image2.jpg', 2048, '.jpg',
         '2025-01-01 11:00:00', 'success', None, None, 'file_id_002', 0, '/uploads/image2.jpg', None),
        (3, '123458', 'CK20250101003', '转库', 'image3.jpg', 3072, '.jpg',
         '2025-01-01 12:00:00', 'success', None, None, 'file_id_003', 0, '/uploads/image3.jpg', None),
        (4, '123459', 'SO20250101004', '销售', 'image4.jpg', 4096, '.jpg',
         '2025-01-01 13:00:00', 'success', None, None, 'file_id_004', 0, '/uploads/image4.jpg', None),
        (5, '123460', 'SO20250101005', '销售', 'image5.jpg', 5120, '.jpg',
         '2025-01-01 14:00:00', 'failed', 'ERR001', '上传失败', None, 1, '/uploads/image5.jpg', None),
        # 已删除的记录
        (6, '123461', 'SO20250101006', '销售', 'image6.jpg', 6144, '.jpg',
         '2025-01-01 15:00:00', 'success', None, None, 'file_id_006', 0, '/uploads/image6.jpg',
         '2025-01-01 16:00:00'),
    ]

    cursor.executemany("""
        INSERT INTO upload_history
        (id, business_id, doc_number, doc_type, file_name, file_size, file_extension,
         upload_time, status, error_code, error_message, yonyou_file_id, retry_count,
         local_file_path, deleted_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, test_records)

    conn.commit()
    conn.close()

    # 设置测试数据库路径（使用mock settings）
    class MockSettings:
        DATABASE_URL = f"sqlite:///{db_path}"

    settings = MockSettings()

    yield db_path, settings

    # 清理测试数据库
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture
def test_files():
    """创建测试文件并返回文件路径列表"""
    temp_dir = tempfile.mkdtemp()
    file_paths = []

    # 创建3个测试文件
    for i in range(1, 4):
        file_path = os.path.join(temp_dir, f'image{i}.jpg')
        with open(file_path, 'wb') as f:
            f.write(b'test image content')
        file_paths.append(file_path)

    yield temp_dir, file_paths

    # 清理测试文件
    for file_path in file_paths:
        if os.path.exists(file_path):
            os.unlink(file_path)
    if os.path.exists(temp_dir):
        os.rmdir(temp_dir)


# ============================================================================
# 单元测试 - DELETE API端点基础功能
# ============================================================================

class TestDeleteAPIBasic:
    """测试DELETE API端点的基础功能"""

    def test_delete_single_record_success(self, test_client, test_db):
        """测试单条记录删除成功"""
        db_path, settings = test_db

        with patch('app.api.admin.get_db_connection', side_effect=create_mock_db_factory(db_path)):
            # 执行删除
            response = delete_records(test_client, [1])

            # 验证响应
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["deleted_count"] == 1
            assert "成功删除1条记录" in data["message"]

            # 验证数据库状态
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT deleted_at FROM upload_history WHERE id = 1")
            row = cursor.fetchone()
            conn.close()

            assert row is not None
            assert row[0] is not None  # deleted_at应该被设置

    def test_delete_batch_records_success(self, test_client, test_db):
        """测试批量删除多条记录成功"""
        db_path, settings = test_db

        with patch('app.api.admin.get_db_connection', side_effect=create_mock_db_factory(db_path)):
            # 批量删除3条记录
            response = delete_records(test_client, [1, 2, 3])

            # 验证响应
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["deleted_count"] == 3
            assert "成功删除3条记录" in data["message"]

            # 验证所有记录都被软删除
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM upload_history
                WHERE id IN (1, 2, 3) AND deleted_at IS NOT NULL
            """)
            count = cursor.fetchone()[0]
            conn.close()

            assert count == 3

    def test_delete_nonexistent_record(self, test_client, test_db):
        """测试删除不存在的记录（幂等性验证）"""
        db_path, settings = test_db

        with patch('app.api.admin.get_db_connection', side_effect=create_mock_db_factory(db_path)):
            # 删除不存在的记录ID
            response = delete_records(test_client, [9999])

            # 验证响应（应该成功，但deleted_count为0）
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["deleted_count"] == 0
            assert "成功删除0条记录" in data["message"]

    def test_delete_already_deleted_record(self, test_client, test_db):
        """测试重复删除已删除的记录（幂等性验证）"""
        db_path, settings = test_db

        with patch('app.api.admin.get_db_connection', side_effect=create_mock_db_factory(db_path)):
            # 第一次删除
            response1 = delete_records(test_client, [1])
            assert response1.json()["deleted_count"] == 1

            # 第二次删除同一记录
            response2 = delete_records(test_client, [1])

            # 验证幂等性：第二次删除返回成功，但deleted_count为0
            assert response2.status_code == 200
            data = response2.json()
            assert data["success"] is True
            assert data["deleted_count"] == 0


# ============================================================================
# 边界条件测试
# ============================================================================

class TestDeleteAPIEdgeCases:
    """测试DELETE API端点的边界条件"""

    def test_delete_empty_ids_list(self, test_client, test_db):
        """测试空ID列表验证"""
        db_path, settings = test_db

        with patch('app.api.admin.get_db_connection', side_effect=create_mock_db_factory(db_path)):
            response = delete_records(test_client, [])

            # 验证返回400错误
            assert response.status_code == 400
            assert "至少选择一条记录" in response.json()["detail"]

    def test_delete_invalid_id_negative(self, test_client, test_db):
        """测试无效ID：负数"""
        db_path, settings = test_db

        with patch('app.api.admin.get_db_connection', side_effect=create_mock_db_factory(db_path)):
            response = delete_records(test_client, [-1])

            # 验证返回400错误
            assert response.status_code == 400
            assert "无效的记录ID" in response.json()["detail"]

    def test_delete_invalid_id_zero(self, test_client, test_db):
        """测试无效ID：0"""
        db_path, settings = test_db

        with patch('app.api.admin.get_db_connection', side_effect=create_mock_db_factory(db_path)):
            response = delete_records(test_client, [0])

            # 验证返回400错误
            assert response.status_code == 400
            assert "无效的记录ID" in response.json()["detail"]

    def test_delete_mixed_valid_invalid_ids(self, test_client, test_db):
        """测试混合有效和无效ID"""
        db_path, settings = test_db

        with patch('app.api.admin.get_db_connection', side_effect=create_mock_db_factory(db_path)):
            response = delete_records(test_client, [1, -1, 2])

            # 验证返回400错误（有任何无效ID就应该拒绝）
            assert response.status_code == 400
            assert "无效的记录ID" in response.json()["detail"]

    def test_delete_batch_partial_exist(self, test_client, test_db):
        """测试批量删除时部分ID不存在"""
        db_path, settings = test_db

        with patch('app.api.admin.get_db_connection', side_effect=create_mock_db_factory(db_path)):
            # 删除3个ID，其中1个存在，2个不存在
            response = delete_records(test_client, [1, 9998, 9999])

            # 验证响应
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["deleted_count"] == 1  # 只有1个记录被删除

            # 验证数据库状态
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT deleted_at FROM upload_history WHERE id = 1")
            row = cursor.fetchone()
            conn.close()

            assert row[0] is not None


# ============================================================================
# 软删除策略验证
# ============================================================================

class TestSoftDeleteStrategy:
    """测试软删除策略的正确实现"""

    def test_soft_delete_sets_deleted_at(self, test_client, test_db):
        """测试软删除设置deleted_at字段"""
        db_path, settings = test_db

        with patch('app.api.admin.get_db_connection', side_effect=create_mock_db_factory(db_path)):
            # 记录删除前的时间
            before_delete = datetime.now()

            # 执行删除
            response = delete_records(test_client, [1])

            # 记录删除后的时间
            after_delete = datetime.now()

            assert response.status_code == 200

            # 验证deleted_at字段被正确设置
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT deleted_at FROM upload_history WHERE id = 1")
            row = cursor.fetchone()
            conn.close()

            assert row is not None
            deleted_at_str = row[0]
            assert deleted_at_str is not None

            # 验证时间戳在合理范围内
            deleted_at = datetime.fromisoformat(deleted_at_str)
            assert before_delete <= deleted_at <= after_delete

    def test_soft_delete_preserves_record(self, test_client, test_db):
        """测试软删除保留数据库记录（不物理删除）"""
        db_path, settings = test_db

        with patch('app.api.admin.get_db_connection', side_effect=create_mock_db_factory(db_path)):
            # 获取删除前的记录内容
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, business_id, doc_number, doc_type, file_name, file_size
                FROM upload_history WHERE id = 1
            """)
            before_delete = cursor.fetchone()
            conn.close()

            # 执行删除
            response = delete_records(test_client, [1])
            assert response.status_code == 200

            # 验证记录仍然存在，且内容未变
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, business_id, doc_number, doc_type, file_name, file_size, deleted_at
                FROM upload_history WHERE id = 1
            """)
            after_delete = cursor.fetchone()
            conn.close()

            # 记录应该仍然存在
            assert after_delete is not None
            # 业务数据应该完全一致
            assert before_delete[0] == after_delete[0]  # id
            assert before_delete[1] == after_delete[1]  # business_id
            assert before_delete[2] == after_delete[2]  # doc_number
            assert before_delete[3] == after_delete[3]  # doc_type
            assert before_delete[4] == after_delete[4]  # file_name
            assert before_delete[5] == after_delete[5]  # file_size
            # deleted_at应该被设置
            assert after_delete[6] is not None

    def test_soft_delete_multiple_times(self, test_client, test_db):
        """测试多次删除同一记录时deleted_at不变"""
        db_path, settings = test_db

        with patch('app.api.admin.get_db_connection', side_effect=create_mock_db_factory(db_path)):
            # 第一次删除
            response1 = delete_records(test_client, [1])
            assert response1.status_code == 200

            # 获取第一次删除的时间戳
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT deleted_at FROM upload_history WHERE id = 1")
            first_deleted_at = cursor.fetchone()[0]
            conn.close()

            # 第二次删除
            response2 = delete_records(test_client, [1])
            assert response2.status_code == 200

            # 获取第二次删除后的时间戳
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT deleted_at FROM upload_history WHERE id = 1")
            second_deleted_at = cursor.fetchone()[0]
            conn.close()

            # 验证deleted_at没有改变（因为WHERE条件包含deleted_at IS NULL）
            assert first_deleted_at == second_deleted_at


# ============================================================================
# 查询过滤验证
# ============================================================================

class TestQueryFiltering:
    """测试已删除记录在各种查询中被正确过滤"""

    def test_deleted_records_not_in_list(self, test_client, test_db):
        """测试已删除记录不在列表查询结果中"""
        db_path, settings = test_db

        with patch('app.api.admin.get_db_connection', side_effect=create_mock_db_factory(db_path)):
            # 删除记录ID=1
            delete_response = delete_records(test_client, [1])
            assert delete_response.status_code == 200

            # 查询记录列表
            list_response = test_client.get("/api/admin/records?page=1&page_size=20")
            assert list_response.status_code == 200

            data = list_response.json()
            records = data["records"]

            # 验证已删除记录不在结果中
            record_ids = [r["id"] for r in records]
            assert 1 not in record_ids

    def test_deleted_records_not_in_statistics(self, test_client, test_db):
        """测试已删除记录不计入统计数据"""
        db_path, settings = test_db

        with patch('app.api.admin.get_db_connection', side_effect=create_mock_db_factory(db_path)):
            # 获取删除前的统计数据
            stats_before = test_client.get("/api/admin/statistics")
            assert stats_before.status_code == 200
            before_data = stats_before.json()

            # 删除2条成功记录
            delete_response = delete_records(test_client, [1, 2])
            assert delete_response.status_code == 200

            # 获取删除后的统计数据
            stats_after = test_client.get("/api/admin/statistics")
            assert stats_after.status_code == 200
            after_data = stats_after.json()

            # 验证总数减少2
            assert after_data["total_uploads"] == before_data["total_uploads"] - 2
            # 验证成功数减少2
            assert after_data["success_count"] == before_data["success_count"] - 2

    def test_deleted_records_not_in_export(self, test_client, test_db):
        """测试已删除记录不包含在导出结果中"""
        db_path, settings = test_db

        with patch('app.api.admin.get_db_connection', side_effect=create_mock_db_factory(db_path)):
            # 删除记录ID=1
            delete_response = delete_records(test_client, [1])
            assert delete_response.status_code == 200

            # 尝试导出（注意：实际导出会创建ZIP文件，这里主要测试不报错）
            # 由于导出功能涉及文件系统操作，这里只验证API调用成功
            export_response = test_client.get("/api/admin/export")

            # 验证导出成功（返回ZIP文件）
            assert export_response.status_code == 200
            assert export_response.headers["content-type"] == "application/zip"

    def test_pre_deleted_record_not_visible(self, test_client, test_db):
        """测试数据库中已存在的deleted_at记录不可见"""
        db_path, settings = test_db

        with patch('app.api.admin.get_db_connection', side_effect=create_mock_db_factory(db_path)):
            # 查询记录列表
            response = test_client.get("/api/admin/records?page=1&page_size=100")
            assert response.status_code == 200

            data = response.json()
            records = data["records"]
            record_ids = [r["id"] for r in records]

            # 验证ID=6的预删除记录不在结果中
            assert 6 not in record_ids


# ============================================================================
# 本地文件保留验证
# ============================================================================

class TestLocalFilePreservation:
    """测试删除记录后本地文件被保留"""

    def test_delete_does_not_remove_local_file(self, test_client, test_db, test_files):
        """测试删除记录后本地文件未被删除"""
        db_path, settings = test_db
        temp_dir, file_paths = test_files

        with patch('app.api.admin.get_db_connection', side_effect=create_mock_db_factory(db_path)):
            # 更新数据库记录，指向真实的测试文件
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE upload_history
                SET local_file_path = ?
                WHERE id = 1
            """, (file_paths[0],))
            conn.commit()
            conn.close()

            # 验证文件存在
            assert os.path.exists(file_paths[0])

            # 执行删除
            response = delete_records(test_client, [1])
            assert response.status_code == 200

            # 验证文件仍然存在
            assert os.path.exists(file_paths[0])

            # 验证文件内容未变
            with open(file_paths[0], 'rb') as f:
                content = f.read()
                assert content == b'test image content'

    def test_batch_delete_preserves_all_files(self, test_client, test_db, test_files):
        """测试批量删除后所有本地文件都被保留"""
        db_path, settings = test_db
        temp_dir, file_paths = test_files

        with patch('app.api.admin.get_db_connection', side_effect=create_mock_db_factory(db_path)):
            # 更新数据库记录，指向真实的测试文件
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            for i, file_path in enumerate(file_paths, start=1):
                cursor.execute("""
                    UPDATE upload_history
                    SET local_file_path = ?
                    WHERE id = ?
                """, (file_path, i))
            conn.commit()
            conn.close()

            # 验证所有文件存在
            for file_path in file_paths:
                assert os.path.exists(file_path)

            # 批量删除
            response = delete_records(test_client, [1, 2, 3])
            assert response.status_code == 200

            # 验证所有文件仍然存在
            for file_path in file_paths:
                assert os.path.exists(file_path)


# ============================================================================
# 集成测试场景
# ============================================================================

class TestDeleteIntegration:
    """测试删除功能的完整集成场景"""

    def test_complete_delete_workflow(self, test_client, test_db):
        """测试完整的删除工作流"""
        db_path, settings = test_db

        with patch('app.api.admin.get_db_connection', side_effect=create_mock_db_factory(db_path)):
            # 1. 获取初始统计数据
            stats_initial = test_client.get("/api/admin/statistics").json()
            initial_total = stats_initial["total_uploads"]

            # 2. 获取初始列表
            list_initial = test_client.get("/api/admin/records?page=1&page_size=20").json()
            initial_count = len(list_initial["records"])

            # 3. 删除1条记录
            delete_response = delete_records(test_client, [1])
            assert delete_response.status_code == 200
            assert delete_response.json()["deleted_count"] == 1

            # 4. 验证统计数据更新
            stats_after = test_client.get("/api/admin/statistics").json()
            assert stats_after["total_uploads"] == initial_total - 1

            # 5. 验证列表数据更新
            list_after = test_client.get("/api/admin/records?page=1&page_size=20").json()
            assert len(list_after["records"]) == initial_count - 1

            # 6. 验证已删除记录不在列表中
            record_ids = [r["id"] for r in list_after["records"]]
            assert 1 not in record_ids

    def test_delete_with_filters(self, test_client, test_db):
        """测试删除后筛选功能仍正常工作"""
        db_path, settings = test_db

        with patch('app.api.admin.get_db_connection', side_effect=create_mock_db_factory(db_path)):
            # 删除一条销售类型的记录
            delete_response = delete_records(test_client, [1])
            assert delete_response.status_code == 200

            # 筛选销售类型记录
            filter_response = test_client.get(
                "/api/admin/records?page=1&page_size=20&doc_type=销售"
            )
            assert filter_response.status_code == 200

            data = filter_response.json()
            record_ids = [r["id"] for r in data["records"]]

            # 验证已删除记录不在筛选结果中
            assert 1 not in record_ids
            # 验证其他销售记录仍在
            assert 2 in record_ids
            assert 4 in record_ids

    def test_delete_with_pagination(self, test_client, test_db):
        """测试删除后分页功能正常"""
        db_path, settings = test_db

        with patch('app.api.admin.get_db_connection', side_effect=create_mock_db_factory(db_path)):
            # 获取删除前的总页数
            before = test_client.get("/api/admin/records?page=1&page_size=2").json()
            before_total_pages = before["total_pages"]
            before_total = before["total"]

            # 删除1条记录
            delete_response = delete_records(test_client, [1])
            assert delete_response.status_code == 200

            # 获取删除后的分页信息
            after = test_client.get("/api/admin/records?page=1&page_size=2").json()
            after_total = after["total"]

            # 验证总数减少
            assert after_total == before_total - 1


# ============================================================================
# 并发测试
# ============================================================================

class TestConcurrentDelete:
    """测试并发删除场景"""

    def test_concurrent_delete_same_record(self, test_client, test_db):
        """测试并发删除同一记录的幂等性"""
        db_path, settings = test_db

        with patch('app.api.admin.get_db_connection', side_effect=create_mock_db_factory(db_path)):
            # 模拟两个并发请求删除同一记录
            response1 = delete_records(test_client, [1])

            response2 = delete_records(test_client, [1])

            # 两个请求都应该返回成功
            assert response1.status_code == 200
            assert response2.status_code == 200

            # 第一个请求删除成功
            assert response1.json()["deleted_count"] == 1
            # 第二个请求因为记录已删除，deleted_count为0
            assert response2.json()["deleted_count"] == 0

            # 验证数据库中记录只被标记删除一次
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM upload_history
                WHERE id = 1 AND deleted_at IS NOT NULL
            """)
            count = cursor.fetchone()[0]
            conn.close()

            assert count == 1

    def test_concurrent_delete_different_records(self, test_client, test_db):
        """测试并发删除不同记录"""
        db_path, settings = test_db

        with patch('app.api.admin.get_db_connection', side_effect=create_mock_db_factory(db_path)):
            # 并发删除不同的记录
            response1 = delete_records(test_client, [1])

            response2 = delete_records(test_client, [2])

            # 两个请求都应该成功
            assert response1.status_code == 200
            assert response2.status_code == 200

            assert response1.json()["deleted_count"] == 1
            assert response2.json()["deleted_count"] == 1

            # 验证两条记录都被删除
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM upload_history
                WHERE id IN (1, 2) AND deleted_at IS NOT NULL
            """)
            count = cursor.fetchone()[0]
            conn.close()

            assert count == 2


# ============================================================================
# 错误处理测试
# ============================================================================

class TestDeleteErrorHandling:
    """测试删除功能的错误处理"""

    def test_delete_with_invalid_request_body(self, test_client, test_db):
        """测试无效的请求体格式"""
        db_path, settings = test_db

        with patch('app.api.admin.get_db_connection', side_effect=create_mock_db_factory(db_path)):
            # 发送无效的请求体（缺少ids字段）
            response = test_client.request(
                method="DELETE",
                url="/api/admin/records",
                content=json.dumps({}),
                headers={"Content-Type": "application/json"}
            )

            # 验证返回422错误（Pydantic验证失败）
            assert response.status_code == 422

    def test_delete_with_wrong_data_type(self, test_client, test_db):
        """测试错误的数据类型"""
        db_path, settings = test_db

        with patch('app.api.admin.get_db_connection', side_effect=create_mock_db_factory(db_path)):
            # 发送字符串而不是整数数组
            response = test_client.request(
                method="DELETE",
                url="/api/admin/records",
                content=json.dumps({"ids": "1,2,3"}),
                headers={"Content-Type": "application/json"}
            )

            # 验证返回422错误
            assert response.status_code == 422

    def test_delete_database_error_rollback(self, test_client, test_db):
        """测试数据库错误时的事务回滚"""
        db_path, settings = test_db

        with patch('app.api.admin.get_db_connection', side_effect=create_mock_db_factory(db_path)):
            # 模拟数据库错误（通过损坏数据库连接）
            with patch('app.api.admin.get_db_connection') as mock_conn:
                mock_cursor = mock_conn.return_value.cursor.return_value
                mock_cursor.execute.side_effect = Exception("Database error")

                response = delete_records(test_client, [1])

                # 验证返回500错误
                assert response.status_code == 500
                assert "删除失败" in response.json()["detail"]

                # 验证rollback被调用
                mock_conn.return_value.rollback.assert_called_once()
