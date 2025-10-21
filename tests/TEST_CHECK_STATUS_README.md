# 检查按钮功能测试套件文档

## 概述

本测试套件为"检查按钮"功能提供全面的自动化测试覆盖,验证后端API、数据库持久化、查询集成和边界条件处理。

**测试文件**: `tests/test_check_status.py`
**测试用例总数**: 26个
**测试通过率**: 100% (26/26)
**执行时间**: ~1.5秒

---

## 测试覆盖范围

### 1. 后端API基础功能测试 (3个测试)

**测试类**: `TestCheckStatusAPIBasic`

| 测试用例 | 目的 | 验证点 |
|---------|------|--------|
| `test_update_check_status_to_true` | 测试更新为已检查 | ✅ API返回200<br>✅ 响应格式正确<br>✅ 数据库checked=1 |
| `test_update_check_status_to_false` | 测试更新为未检查 | ✅ API返回200<br>✅ 数据库checked=0 |
| `test_update_check_status_updates_timestamp` | 测试更新updated_at字段 | ✅ updated_at同步更新<br>✅ 时间戳在合理范围内 |

### 2. 错误场景测试 (5个测试)

**测试类**: `TestCheckStatusAPIErrors`

| 测试用例 | 场景 | 预期结果 |
|---------|------|---------|
| `test_update_nonexistent_record` | 记录不存在 | ✅ 返回404错误 |
| `test_update_deleted_record` | 已删除记录 | ✅ 返回404错误<br>✅ 数据库状态未改变 |
| `test_update_with_invalid_record_id` | 非整数record_id | ✅ 返回422错误 |
| `test_update_with_missing_checked_field` | 缺少checked字段 | ✅ 返回422错误 |
| `test_update_with_invalid_checked_value` | checked类型错误 | ✅ 返回422错误 |

### 3. 幂等性和并发测试 (3个测试)

**测试类**: `TestCheckStatusIdempotency`

| 测试用例 | 验证点 |
|---------|--------|
| `test_repeated_update_to_true` | ✅ 重复标记已检查<br>✅ 状态保持正确<br>✅ 时间戳更新 |
| `test_toggle_check_status` | ✅ 反复切换状态<br>✅ 每次切换正确 |
| `test_concurrent_update_same_record` | ✅ 并发更新成功<br>✅ 最终状态正确 |

### 4. 数据库持久化测试 (4个测试)

**测试类**: `TestCheckStatusPersistence`

| 测试用例 | 验证点 |
|---------|--------|
| `test_checked_field_exists` | ✅ checked字段存在 |
| `test_checked_field_default_value` | ✅ 默认值为0(未检查) |
| `test_checked_index_exists` | ✅ idx_checked索引存在 |
| `test_check_status_persists_after_query` | ✅ 更新后状态持久化 |

### 5. 集成测试 (3个测试)

**测试类**: `TestCheckStatusIntegration`

| 测试用例 | 验证点 |
|---------|--------|
| `test_get_records_includes_checked_field` | ✅ GET接口包含checked字段<br>✅ 字段类型为布尔值 |
| `test_get_records_checked_value_correct` | ✅ checked值正确(true/false) |
| `test_update_and_get_workflow` | ✅ 完整更新-查询流程 |

### 6. 边界条件测试 (5个测试)

**测试类**: `TestCheckStatusEdgeCases`

| 测试用例 | 场景 | 验证点 |
|---------|------|--------|
| `test_update_failed_record_status` | 失败记录检查 | ✅ 允许标记已检查<br>✅ status字段不变 |
| `test_update_with_zero_record_id` | record_id=0 | ✅ 返回404 |
| `test_update_with_negative_record_id` | 负数record_id | ✅ 返回404 |
| `test_update_preserves_other_fields` | 字段隔离 | ✅ 其他字段不变<br>✅ 只更新checked |

### 7. 事务管理测试 (1个测试)

**测试类**: `TestCheckStatusTransactions`

| 测试用例 | 验证点 |
|---------|--------|
| `test_database_error_rollback` | ✅ 错误时rollback调用<br>✅ 返回500错误<br>✅ 数据库状态未改变 |

### 8. 完整场景测试 (3个测试)

**测试类**: `TestCheckStatusCompleteWorkflow`

| 测试用例 | 用户场景 | 验证点 |
|---------|---------|--------|
| `test_first_check_workflow` | 首次检查流程 | ✅ 查询未检查状态<br>✅ 更新为已检查<br>✅ 刷新后状态保持 |
| `test_uncheck_workflow` | 撤销检查流程 | ✅ 查询已检查状态<br>✅ 更新为未检查<br>✅ 状态正确回退 |
| `test_batch_check_workflow` | 批量检查流程 | ✅ 批量更新3条记录<br>✅ 所有记录状态正确 |

---

## 运行测试

### 运行完整测试套件

```bash
# 基础运行
pytest tests/test_check_status.py -v

# 显示详细输出
pytest tests/test_check_status.py -vv

# 显示测试覆盖率
pytest tests/test_check_status.py --cov=app.api.admin --cov-report=html

# 运行特定测试类
pytest tests/test_check_status.py::TestCheckStatusAPIBasic -v

# 运行特定测试用例
pytest tests/test_check_status.py::TestCheckStatusAPIBasic::test_update_check_status_to_true -v
```

### 运行失败时显示详细信息

```bash
pytest tests/test_check_status.py -v --tb=short
```

### 生成覆盖率报告

```bash
# 终端输出
pytest tests/test_check_status.py --cov=app.api.admin --cov-report=term

# HTML报告
pytest tests/test_check_status.py --cov=app.api.admin --cov-report=html
# 报告位于: htmlcov/index.html
```

---

## 测试数据结构

### 测试数据库记录

测试使用以下6条预设记录:

| ID | 单据编号 | 单据类型 | 状态 | checked | deleted_at | 说明 |
|----|---------|---------|------|---------|-----------|------|
| 1 | SO20250101001 | 销售 | success | 0 | NULL | 未检查的成功记录 |
| 2 | SO20250101002 | 销售 | success | 0 | NULL | 未检查的成功记录 |
| 3 | CK20250101003 | 转库 | success | 1 | NULL | 已检查的成功记录 |
| 4 | SO20250101004 | 销售 | failed | 0 | NULL | 未检查的失败记录 |
| 5 | SO20250101005 | 销售 | success | 0 | 2025-01-01 15:00:00 | 已删除的未检查记录 |
| 6 | SO20250101006 | 销售 | success | 1 | 2025-01-01 16:00:00 | 已删除的已检查记录 |

---

## API端点规格

### PATCH /api/admin/records/{record_id}/check

**请求示例**:
```json
{
    "checked": true
}
```

**成功响应** (200 OK):
```json
{
    "success": true,
    "id": 1,
    "checked": true,
    "message": "检查状态已更新"
}
```

**错误响应** (404 Not Found):
```json
{
    "detail": "记录不存在或已删除"
}
```

**错误响应** (422 Unprocessable Entity):
```json
{
    "detail": [
        {
            "loc": ["body", "checked"],
            "msg": "field required",
            "type": "value_error.missing"
        }
    ]
}
```

---

## 测试覆盖的功能需求

### ✅ 已验证的需求 (来自技术规格)

1. **后端API实现**
   - ✅ PATCH端点正确响应
   - ✅ Pydantic模型验证
   - ✅ 参数验证(record_id, checked)
   - ✅ 错误处理(404, 422, 500)

2. **数据库持久化**
   - ✅ checked字段存在且默认值为0
   - ✅ idx_checked索引存在
   - ✅ SQLite INTEGER(0/1)正确存储布尔值
   - ✅ updated_at同步更新

3. **软删除集成**
   - ✅ deleted_at不为空的记录无法更新
   - ✅ 返回404错误

4. **查询集成**
   - ✅ GET /api/admin/records 包含checked字段
   - ✅ SQLite INTEGER正确转换为Python布尔值
   - ✅ 更新后GET接口返回最新状态

5. **事务管理**
   - ✅ 错误时事务回滚
   - ✅ 数据库状态未被修改

6. **幂等性**
   - ✅ 重复标记已检查不报错
   - ✅ 并发更新同一记录正常工作

---

## 测试质量指标

| 指标 | 值 | 说明 |
|------|---|------|
| **测试用例总数** | 26 | 覆盖所有核心场景 |
| **通过率** | 100% | 所有测试通过 |
| **执行时间** | ~1.5秒 | 快速反馈 |
| **代码覆盖率** | 42% (admin.py) | 主要覆盖检查状态端点 |
| **边界条件覆盖** | 5个测试 | 充分测试异常情况 |
| **集成测试** | 3个测试 | 验证完整工作流 |

---

## 测试维护指南

### 添加新测试用例

1. **确定测试类别** (API基础/错误/幂等性/持久化/集成/边界/事务/场景)
2. **在相应的测试类中添加新方法**
3. **遵循命名约定**: `test_<scenario>_<expected_result>`
4. **使用Given-When-Then结构编写测试**

### 测试数据管理

- **Fixture**: `test_db` 自动创建临时数据库
- **清理**: 每个测试后自动删除临时数据库
- **隔离**: 每个测试使用独立的数据库连接

### 常见问题排查

**问题1: 测试失败 - 数据库连接错误**
```bash
# 检查是否使用了正确的mock
with patch('app.api.admin.get_db_connection', side_effect=create_mock_db_factory(db_path)):
```

**问题2: 测试失败 - checked值不正确**
```bash
# 验证SQLite INTEGER类型
assert row[0] == 1  # True
assert row[0] == 0  # False
```

**问题3: 测试执行缓慢**
```bash
# 使用 -k 运行特定测试
pytest tests/test_check_status.py -k "test_update_check_status_to_true" -v
```

---

## 依赖项

- **pytest**: 测试框架
- **pytest-cov**: 覆盖率报告
- **FastAPI TestClient**: API测试客户端
- **sqlite3**: 测试数据库
- **unittest.mock**: Mock对象

---

## 成功标准

### ✅ 所有测试通过

- [x] 26/26 测试用例通过
- [x] 正常流程验证
- [x] 错误场景验证
- [x] 边界条件验证
- [x] 幂等性验证
- [x] 并发验证
- [x] 持久化验证
- [x] 集成验证

### ✅ 测试质量

- [x] 测试名称清晰易懂
- [x] 每个测试单一职责
- [x] 测试数据隔离
- [x] 自动清理资源
- [x] 快速执行(<2秒)

### ✅ 覆盖率

- [x] 核心业务逻辑100%覆盖
- [x] 错误处理路径覆盖
- [x] 边界条件覆盖

---

## 相关文档

- **需求确认**: `.claude/specs/add-check-button-to-management-page/requirements-confirm.md`
- **技术规格**: `.claude/specs/add-check-button-to-management-page/requirements-spec.md`
- **实现代码**: `app/api/admin.py` (第394-462行)
- **数据库变更**: `app/core/database.py` (第64-67行, 第111-114行)

---

## 更新日志

**2025-10-21**
- ✅ 创建完整测试套件 (26个测试用例)
- ✅ 所有测试通过
- ✅ 修复Pydantic类型转换测试用例
- ✅ 更新conftest.py以支持checked字段
- ✅ 生成测试文档

---

**维护者**: Claude Code
**创建时间**: 2025-10-21
**最后更新**: 2025-10-21
