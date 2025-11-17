import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.database import get_db_connection


@pytest.fixture
def test_client():
    """测试客户端"""
    return TestClient(app)


@pytest.fixture
def setup_test_data():
    """准备测试数据"""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # 插入测试数据
        test_records = [
            ("BID001", "天津佳士达物流有限公司", "success"),
            ("BID002", "天津佳士达物流有限公司", "success"),
            ("BID003", "顺丰速运", "success"),
            ("BID004", None, "success"),  # 物流信息未获取
        ]

        for business_id, logistics, status in test_records:
            cursor.execute("""
                INSERT INTO upload_history
                (business_id, file_name, file_size, upload_time, status, logistics)
                VALUES (?, 'test.jpg', 1024, datetime('now'), ?, ?)
            """, (business_id, status, logistics))

        conn.commit()

    yield

    # 清理测试数据
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM upload_history WHERE business_id LIKE 'BID%'")
        conn.commit()


def test_logistics_filter_all(test_client, setup_test_data):
    """测试'全部物流'筛选(不传递logistics参数)"""
    # 不传递logistics参数,或者传递"全部物流"都应该返回所有记录
    response = test_client.get("/api/admin/records")

    assert response.status_code == 200
    data = response.json()

    # 应至少包含测试数据的4条记录
    assert len(data['records']) >= 4
    # 验证测试数据存在
    business_ids = [r['business_id'] for r in data['records']]
    assert 'BID001' in business_ids
    assert 'BID002' in business_ids
    assert 'BID003' in business_ids
    assert 'BID004' in business_ids


def test_logistics_filter_specific(test_client, setup_test_data):
    """测试特定物流公司筛选"""
    response = test_client.get("/api/admin/records?logistics=天津佳士达物流有限公司")

    assert response.status_code == 200
    data = response.json()

    # 应返回2条记录
    assert len(data['records']) == 2
    assert all(r['logistics'] == '天津佳士达物流有限公司' for r in data['records'])


def test_logistics_options_api(test_client, setup_test_data):
    """测试物流选项API"""
    response = test_client.get("/api/admin/logistics-options")

    assert response.status_code == 200
    data = response.json()

    # 应包含"全部物流" + 2个不重复的物流公司
    assert "全部物流" in data['logistics_list']
    assert "天津佳士达物流有限公司" in data['logistics_list']
    assert "顺丰速运" in data['logistics_list']
    assert len(data['logistics_list']) == 3  # 全部 + 天津佳士达 + 顺丰
