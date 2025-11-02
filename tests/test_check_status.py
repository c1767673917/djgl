"""测试检查按钮功能

本测试文件专注于验证检查状态管理功能的以下核心方面:
1. 后端API功能验证(更新检查状态)
2. 数据库持久化验证(checked字段和索引)
3. 查询集成验证(GET接口返回checked字段)
4. 边界条件和错误处理
5. 并发更新和幂等性验证
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
from app.core.timezone import get_beijing_now_naive


# ============================================================================
# 测试装置 (Fixtures)
# ============================================================================

@pytest.fixture
def test_client():
    """创建FastAPI测试客户端"""
    return TestClient(app)


def create_mock_db_factory(db_path):
    """辅助函数: 创建返回测试数据库连接的工厂函数"""
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
            product_type TEXT DEFAULT NULL,
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
            updated_at DATETIME,
            deleted_at DATETIME DEFAULT NULL,
            checked INTEGER DEFAULT 0
        )
    """)

    # 创建索引
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_checked
        ON upload_history(checked)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_deleted_at
        ON upload_history(deleted_at)
    """)

    # 插入测试数据
    test_records = [
        # 未检查的记录
        (1, '123456', 'SO20250101001', '销售', '油脂', 'image1.jpg', 1024, '.jpg',
         '2025-01-01 10:00:00', 'success', None, None, 'file_id_001', 0, '/uploads/image1.jpg',
         '2025-01-01 10:00:00', '2025-01-01 10:00:00', None, 0),
        (2, '123457', 'SO20250101002', '销售', '快消', 'image2.jpg', 2048, '.jpg',
         '2025-01-01 11:00:00', 'success', None, None, 'file_id_002', 0, '/uploads/image2.jpg',
         '2025-01-01 11:00:00', '2025-01-01 11:00:00', None, 0),
        # 已检查的记录
        (3, '123458', 'CK20250101003', '转库', '油脂', 'image3.jpg', 3072, '.jpg',
         '2025-01-01 12:00:00', 'success', None, None, 'file_id_003', 0, '/uploads/image3.jpg',
         '2025-01-01 12:00:00', '2025-01-01 12:00:00', None, 1),
        # 失败的记录(未检查)
        (4, '123459', 'SO20250101004', '销售', '油脂', 'image4.jpg', 4096, '.jpg',
         '2025-01-01 13:00:00', 'failed', 'ERR001', '上传失败', None, 1, '/uploads/image4.jpg',
         '2025-01-01 13:00:00', '2025-01-01 13:00:00', None, 0),
        # 已删除的记录(未检查)
        (5, '123460', 'SO20250101005', '销售', '快消', 'image5.jpg', 5120, '.jpg',
         '2025-01-01 14:00:00', 'success', None, None, 'file_id_005', 0, '/uploads/image5.jpg',
         '2025-01-01 14:00:00', '2025-01-01 14:00:00', '2025-01-01 15:00:00', 0),
        # 已删除且已检查的记录
        (6, '123461', 'SO20250101006', '销售', '油脂', 'image6.jpg', 6144, '.jpg',
         '2025-01-01 15:00:00', 'success', None, None, 'file_id_006', 0, '/uploads/image6.jpg',
         '2025-01-01 15:00:00', '2025-01-01 15:00:00', '2025-01-01 16:00:00', 1),
    ]

    cursor.executemany("""
        INSERT INTO upload_history
        (id, business_id, doc_number, doc_type, product_type, file_name, file_size, file_extension,
         upload_time, status, error_code, error_message, yonyou_file_id, retry_count,
         local_file_path, created_at, updated_at, deleted_at, checked)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, test_records)

    conn.commit()
    conn.close()

    yield db_path

    # 清理测试数据库
    if os.path.exists(db_path):
        os.unlink(db_path)


# ============================================================================
# 单元测试 - PATCH API端点基础功能
# ============================================================================

class TestCheckStatusAPIBasic:
    """测试检查状态API端点的基础功能"""

    def test_update_check_status_to_true(self, test_client, test_db):
        """测试: 将检查状态更新为已检查"""
        db_path = test_db

        with patch('app.api.admin.get_db_connection', side_effect=create_mock_db_factory(db_path)):
            # 执行更新: 未检查 -> 已检查
            response = test_client.patch(
                "/api/admin/records/1/check",
                json={"checked": True}
            )

            # 验证响应
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["id"] == 1
            assert data["checked"] is True
            assert "检查状态已更新" in data["message"]

            # 验证数据库状态
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT checked FROM upload_history WHERE id = 1")
            row = cursor.fetchone()
            conn.close()

            assert row is not None
            assert row[0] == 1  # SQLite: 1表示true

    def test_update_check_status_to_false(self, test_client, test_db):
        """测试: 将检查状态更新为未检查"""
        db_path = test_db

        with patch('app.api.admin.get_db_connection', side_effect=create_mock_db_factory(db_path)):
            # 执行更新: 已检查 -> 未检查
            response = test_client.patch(
                "/api/admin/records/3/check",
                json={"checked": False}
            )

            # 验证响应
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["id"] == 3
            assert data["checked"] is False

            # 验证数据库状态
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT checked FROM upload_history WHERE id = 3")
            row = cursor.fetchone()
            conn.close()

            assert row[0] == 0  # SQLite: 0表示false

    def test_update_check_status_updates_timestamp(self, test_client, test_db):
        """测试: 更新检查状态同时更新updated_at字段"""
        db_path = test_db

        with patch('app.api.admin.get_db_connection', side_effect=create_mock_db_factory(db_path)):
            # 获取更新前的时间戳
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT updated_at FROM upload_history WHERE id = 1")
            old_timestamp = cursor.fetchone()[0]
            conn.close()

            # 记录更新前的时间
            before_update = get_beijing_now_naive()

            # 执行更新
            response = test_client.patch(
                "/api/admin/records/1/check",
                json={"checked": True}
            )

            # 记录更新后的时间
            after_update = get_beijing_now_naive()

            assert response.status_code == 200

            # 验证updated_at被更新
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT updated_at FROM upload_history WHERE id = 1")
            new_timestamp = cursor.fetchone()[0]
            conn.close()

            # updated_at应该已改变
            assert new_timestamp != old_timestamp

            # 验证新时间戳在合理范围内
            new_time = datetime.fromisoformat(new_timestamp)
            assert before_update <= new_time <= after_update


# ============================================================================
# 错误场景测试
# ============================================================================

class TestCheckStatusAPIErrors:
    """测试检查状态API的错误场景"""

    def test_update_nonexistent_record(self, test_client, test_db):
        """测试: 更新不存在的记录返回404"""
        db_path = test_db

        with patch('app.api.admin.get_db_connection', side_effect=create_mock_db_factory(db_path)):
            response = test_client.patch(
                "/api/admin/records/99999/check",
                json={"checked": True}
            )

            # 验证返回404错误
            assert response.status_code == 404
            assert "不存在" in response.json()["detail"]

    def test_update_deleted_record(self, test_client, test_db):
        """测试: 更新已删除的记录返回404"""
        db_path = test_db

        with patch('app.api.admin.get_db_connection', side_effect=create_mock_db_factory(db_path)):
            # 尝试更新已删除的记录(id=5)
            response = test_client.patch(
                "/api/admin/records/5/check",
                json={"checked": True}
            )

            # 验证返回404错误
            assert response.status_code == 404
            assert "不存在" in response.json()["detail"] or "已删除" in response.json()["detail"]

            # 验证数据库状态未改变
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT checked FROM upload_history WHERE id = 5")
            row = cursor.fetchone()
            conn.close()

            assert row[0] == 0  # 仍为未检查

    def test_update_with_invalid_record_id(self, test_client, test_db):
        """测试: 无效的record_id(非整数)返回422"""
        db_path = test_db

        with patch('app.api.admin.get_db_connection', side_effect=create_mock_db_factory(db_path)):
            response = test_client.patch(
                "/api/admin/records/abc/check",
                json={"checked": True}
            )

            # 验证返回422错误(参数验证失败)
            assert response.status_code == 422

    def test_update_with_missing_checked_field(self, test_client, test_db):
        """测试: 缺少checked字段返回422"""
        db_path = test_db

        with patch('app.api.admin.get_db_connection', side_effect=create_mock_db_factory(db_path)):
            response = test_client.patch(
                "/api/admin/records/1/check",
                json={}
            )

            # 验证返回422错误
            assert response.status_code == 422

    def test_update_with_invalid_checked_value(self, test_client, test_db):
        """测试: checked字段类型错误(数组)返回422"""
        db_path = test_db

        with patch('app.api.admin.get_db_connection', side_effect=create_mock_db_factory(db_path)):
            # 尝试使用数组(Pydantic无法转换)
            response = test_client.patch(
                "/api/admin/records/1/check",
                json={"checked": [1, 2, 3]}
            )

            # 验证返回422错误
            assert response.status_code == 422


# ============================================================================
# 幂等性和并发测试
# ============================================================================

class TestCheckStatusIdempotency:
    """测试检查状态更新的幂等性"""

    def test_repeated_update_to_true(self, test_client, test_db):
        """测试: 重复标记为已检查(幂等性验证)"""
        db_path = test_db

        with patch('app.api.admin.get_db_connection', side_effect=create_mock_db_factory(db_path)):
            # 第一次更新
            response1 = test_client.patch(
                "/api/admin/records/1/check",
                json={"checked": True}
            )
            assert response1.status_code == 200

            # 获取第一次更新的时间戳
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT checked, updated_at FROM upload_history WHERE id = 1")
            first_state = cursor.fetchone()
            conn.close()

            # 第二次更新(重复操作)
            response2 = test_client.patch(
                "/api/admin/records/1/check",
                json={"checked": True}
            )
            assert response2.status_code == 200

            # 获取第二次更新后的状态
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT checked, updated_at FROM upload_history WHERE id = 1")
            second_state = cursor.fetchone()
            conn.close()

            # 验证状态仍为已检查
            assert second_state[0] == 1
            # 时间戳应该被更新(证明SQL确实执行了)
            assert second_state[1] != first_state[1]

    def test_toggle_check_status(self, test_client, test_db):
        """测试: 反复切换检查状态"""
        db_path = test_db

        with patch('app.api.admin.get_db_connection', side_effect=create_mock_db_factory(db_path)):
            # 循环切换状态
            for i in range(3):
                # 切换为已检查
                response = test_client.patch(
                    "/api/admin/records/1/check",
                    json={"checked": True}
                )
                assert response.status_code == 200

                # 验证状态
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT checked FROM upload_history WHERE id = 1")
                assert cursor.fetchone()[0] == 1
                conn.close()

                # 切换为未检查
                response = test_client.patch(
                    "/api/admin/records/1/check",
                    json={"checked": False}
                )
                assert response.status_code == 200

                # 验证状态
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT checked FROM upload_history WHERE id = 1")
                assert cursor.fetchone()[0] == 0
                conn.close()

    def test_concurrent_update_same_record(self, test_client, test_db):
        """测试: 并发更新同一记录"""
        db_path = test_db

        with patch('app.api.admin.get_db_connection', side_effect=create_mock_db_factory(db_path)):
            # 模拟两个并发请求更新同一记录
            response1 = test_client.patch(
                "/api/admin/records/1/check",
                json={"checked": True}
            )

            response2 = test_client.patch(
                "/api/admin/records/1/check",
                json={"checked": True}
            )

            # 两个请求都应该成功
            assert response1.status_code == 200
            assert response2.status_code == 200

            # 验证最终状态正确
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT checked FROM upload_history WHERE id = 1")
            assert cursor.fetchone()[0] == 1
            conn.close()


# ============================================================================
# 数据库持久化测试
# ============================================================================

class TestCheckStatusPersistence:
    """测试检查状态的数据库持久化"""

    def test_checked_field_exists(self, test_db):
        """测试: checked字段存在"""
        db_path = test_db

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(upload_history)")
        columns = cursor.fetchall()
        conn.close()

        column_names = [col[1] for col in columns]
        assert 'checked' in column_names

    def test_checked_field_default_value(self, test_db):
        """测试: checked字段默认值为0"""
        db_path = test_db

        # 插入新记录(不指定checked值)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO upload_history
            (business_id, doc_number, file_name, file_size, status)
            VALUES (?, ?, ?, ?, ?)
        """, ('999999', 'TEST001', 'test.jpg', 1024, 'success'))
        conn.commit()
        new_id = cursor.lastrowid

        # 验证默认值
        cursor.execute("SELECT checked FROM upload_history WHERE id = ?", [new_id])
        result = cursor.fetchone()
        conn.close()

        assert result[0] == 0  # 默认为未检查

    def test_checked_index_exists(self, test_db):
        """测试: idx_checked索引存在"""
        db_path = test_db

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='index' AND name='idx_checked'
        """)
        result = cursor.fetchone()
        conn.close()

        assert result is not None

    def test_check_status_persists_after_query(self, test_client, test_db):
        """测试: 更新后刷新查询,状态保持"""
        db_path = test_db

        with patch('app.api.admin.get_db_connection', side_effect=create_mock_db_factory(db_path)):
            # 更新状态
            update_response = test_client.patch(
                "/api/admin/records/1/check",
                json={"checked": True}
            )
            assert update_response.status_code == 200

            # 关闭连接模拟刷新
            # (实际上每次请求都会新建连接)

            # 重新查询验证持久化
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT checked FROM upload_history WHERE id = 1")
            result = cursor.fetchone()
            conn.close()

            assert result[0] == 1


# ============================================================================
# 集成测试 - GET接口返回checked字段
# ============================================================================

class TestCheckStatusIntegration:
    """测试检查状态与GET接口的集成"""

    def test_get_records_includes_checked_field(self, test_client, test_db):
        """测试: GET /api/admin/records 包含checked字段"""
        db_path = test_db

        with patch('app.api.admin.get_db_connection', side_effect=create_mock_db_factory(db_path)):
            response = test_client.get("/api/admin/records?page=1&page_size=20")

            assert response.status_code == 200
            data = response.json()

            # 验证响应包含records
            assert "records" in data
            assert len(data["records"]) > 0

            # 验证每条记录都有checked字段
            for record in data["records"]:
                assert "checked" in record
                assert isinstance(record["checked"], bool)

    def test_get_records_checked_value_correct(self, test_client, test_db):
        """测试: GET接口返回的checked值正确"""
        db_path = test_db

        with patch('app.api.admin.get_db_connection', side_effect=create_mock_db_factory(db_path)):
            response = test_client.get("/api/admin/records?page=1&page_size=20")

            assert response.status_code == 200
            data = response.json()

            records = data["records"]

            # 查找ID=1的记录(未检查)
            record_1 = next((r for r in records if r["id"] == 1), None)
            assert record_1 is not None
            assert record_1["checked"] is False

            # 查找ID=3的记录(已检查)
            record_3 = next((r for r in records if r["id"] == 3), None)
            assert record_3 is not None
            assert record_3["checked"] is True

    def test_update_and_get_workflow(self, test_client, test_db):
        """测试: 完整的更新-查询工作流"""
        db_path = test_db

        with patch('app.api.admin.get_db_connection', side_effect=create_mock_db_factory(db_path)):
            # 1. 获取初始状态
            get_response_before = test_client.get("/api/admin/records?page=1&page_size=20")
            records_before = get_response_before.json()["records"]
            record_1_before = next((r for r in records_before if r["id"] == 1), None)
            assert record_1_before["checked"] is False

            # 2. 更新检查状态
            update_response = test_client.patch(
                "/api/admin/records/1/check",
                json={"checked": True}
            )
            assert update_response.status_code == 200

            # 3. 重新查询验证
            get_response_after = test_client.get("/api/admin/records?page=1&page_size=20")
            records_after = get_response_after.json()["records"]
            record_1_after = next((r for r in records_after if r["id"] == 1), None)
            assert record_1_after["checked"] is True


# ============================================================================
# 边界条件测试
# ============================================================================

class TestCheckStatusEdgeCases:
    """测试检查状态功能的边界条件"""

    def test_update_failed_record_status(self, test_client, test_db):
        """测试: 失败记录也可以更新检查状态"""
        db_path = test_db

        with patch('app.api.admin.get_db_connection', side_effect=create_mock_db_factory(db_path)):
            # 更新失败记录(id=4)的检查状态
            response = test_client.patch(
                "/api/admin/records/4/check",
                json={"checked": True}
            )

            # 验证更新成功
            assert response.status_code == 200
            data = response.json()
            assert data["checked"] is True

            # 验证数据库状态
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT checked, status FROM upload_history WHERE id = 4")
            row = cursor.fetchone()
            conn.close()

            assert row[0] == 1  # checked=1
            assert row[1] == 'failed'  # status仍为failed

    def test_update_with_zero_record_id(self, test_client, test_db):
        """测试: record_id=0的边界情况"""
        db_path = test_db

        with patch('app.api.admin.get_db_connection', side_effect=create_mock_db_factory(db_path)):
            response = test_client.patch(
                "/api/admin/records/0/check",
                json={"checked": True}
            )

            # 验证返回404(记录不存在)
            assert response.status_code == 404

    def test_update_with_negative_record_id(self, test_client, test_db):
        """测试: 负数record_id"""
        db_path = test_db

        with patch('app.api.admin.get_db_connection', side_effect=create_mock_db_factory(db_path)):
            response = test_client.patch(
                "/api/admin/records/-1/check",
                json={"checked": True}
            )

            # 验证返回404(记录不存在)
            assert response.status_code == 404

    def test_update_preserves_other_fields(self, test_client, test_db):
        """测试: 更新检查状态不影响其他字段"""
        db_path = test_db

        with patch('app.api.admin.get_db_connection', side_effect=create_mock_db_factory(db_path)):
            # 获取更新前的所有字段
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT business_id, doc_number, file_name, status, checked
                FROM upload_history WHERE id = 1
            """)
            before_update = cursor.fetchone()
            conn.close()

            # 执行更新
            response = test_client.patch(
                "/api/admin/records/1/check",
                json={"checked": True}
            )
            assert response.status_code == 200

            # 验证其他字段未改变
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT business_id, doc_number, file_name, status, checked
                FROM upload_history WHERE id = 1
            """)
            after_update = cursor.fetchone()
            conn.close()

            # 业务数据应该完全一致
            assert before_update[0] == after_update[0]  # business_id
            assert before_update[1] == after_update[1]  # doc_number
            assert before_update[2] == after_update[2]  # file_name
            assert before_update[3] == after_update[3]  # status
            # 只有checked字段改变
            assert before_update[4] == 0
            assert after_update[4] == 1


# ============================================================================
# 事务和回滚测试
# ============================================================================

class TestCheckStatusTransactions:
    """测试检查状态更新的事务管理"""

    def test_database_error_rollback(self, test_client, test_db):
        """测试: 数据库错误时事务回滚"""
        db_path = test_db

        # 获取更新前的状态
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT checked FROM upload_history WHERE id = 1")
        before_state = cursor.fetchone()[0]
        conn.close()

        with patch('app.api.admin.get_db_connection') as mock_conn:
            # 模拟数据库错误
            mock_cursor = mock_conn.return_value.cursor.return_value
            mock_cursor.execute.side_effect = Exception("Database error")

            response = test_client.patch(
                "/api/admin/records/1/check",
                json={"checked": True}
            )

            # 验证返回500错误
            assert response.status_code == 500
            assert "更新失败" in response.json()["detail"]

            # 验证rollback被调用
            mock_conn.return_value.rollback.assert_called_once()

        # 验证数据库状态未改变(回滚成功)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT checked FROM upload_history WHERE id = 1")
        after_state = cursor.fetchone()[0]
        conn.close()

        assert before_state == after_state


# ============================================================================
# 完整场景测试
# ============================================================================

class TestCheckStatusCompleteWorkflow:
    """测试检查按钮功能的完整用户场景"""

    def test_first_check_workflow(self, test_client, test_db):
        """测试: 首次检查流程"""
        db_path = test_db

        with patch('app.api.admin.get_db_connection', side_effect=create_mock_db_factory(db_path)):
            # 1. 获取记录列表,确认未检查
            list_response = test_client.get("/api/admin/records?page=1&page_size=20")
            records = list_response.json()["records"]
            record_1 = next((r for r in records if r["id"] == 1), None)
            assert record_1["checked"] is False

            # 2. 用户点击"检查"按钮,查看图片
            # (前端操作,这里跳过)

            # 3. 用户关闭图片模态框,自动标记为已检查
            check_response = test_client.patch(
                "/api/admin/records/1/check",
                json={"checked": True}
            )
            assert check_response.status_code == 200
            assert check_response.json()["checked"] is True

            # 4. 刷新页面,验证状态保持
            refresh_response = test_client.get("/api/admin/records?page=1&page_size=20")
            records_after = refresh_response.json()["records"]
            record_1_after = next((r for r in records_after if r["id"] == 1), None)
            assert record_1_after["checked"] is True

    def test_uncheck_workflow(self, test_client, test_db):
        """测试: 撤销检查流程"""
        db_path = test_db

        with patch('app.api.admin.get_db_connection', side_effect=create_mock_db_factory(db_path)):
            # 1. 记录当前为已检查状态(id=3)
            list_response = test_client.get("/api/admin/records?page=1&page_size=20")
            records = list_response.json()["records"]
            record_3 = next((r for r in records if r["id"] == 3), None)
            assert record_3["checked"] is True

            # 2. 用户点击"已检查"按钮,确认撤销
            uncheck_response = test_client.patch(
                "/api/admin/records/3/check",
                json={"checked": False}
            )
            assert uncheck_response.status_code == 200
            assert uncheck_response.json()["checked"] is False

            # 3. 验证状态改回未检查
            refresh_response = test_client.get("/api/admin/records?page=1&page_size=20")
            records_after = refresh_response.json()["records"]
            record_3_after = next((r for r in records_after if r["id"] == 3), None)
            assert record_3_after["checked"] is False

    def test_batch_check_workflow(self, test_client, test_db):
        """测试: 批量检查多条记录"""
        db_path = test_db

        with patch('app.api.admin.get_db_connection', side_effect=create_mock_db_factory(db_path)):
            # 批量标记多条记录为已检查
            record_ids = [1, 2, 4]

            for record_id in record_ids:
                response = test_client.patch(
                    f"/api/admin/records/{record_id}/check",
                    json={"checked": True}
                )
                assert response.status_code == 200

            # 验证所有记录都已标记
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM upload_history
                WHERE id IN (1, 2, 4) AND checked = 1
            """)
            count = cursor.fetchone()[0]
            conn.close()

            assert count == 3
