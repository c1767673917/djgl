# 测试说明文档

## 测试概述

本测试套件为单据上传管理系统提供全面的测试覆盖,包括单元测试、集成测试和端到端测试。

## 测试结构

```
tests/
├── __init__.py              # 测试包初始化
├── conftest.py              # Pytest配置和共享fixtures
├── test_yonyou_client.py    # 用友云客户端测试(P0)
├── test_upload_api.py       # 上传API测试(P1)
├── test_history_api.py      # 历史查询API测试(P1)
├── test_database.py         # 数据库测试(P1)
└── test_integration.py      # 集成测试(P2)
```

## 测试覆盖范围

### 1. 用友云客户端测试 (test_yonyou_client.py)

**优先级: P0**

#### 签名算法测试
- ✅ 签名格式正确性
- ✅ 签名一致性验证
- ✅ 不同时间戳签名差异
- ✅ 算法正确性(手动验证)
- ✅ URL编码验证

#### Token管理测试
- ✅ Token首次获取成功
- ✅ Token缓存机制
- ✅ force_refresh强制刷新
- ✅ Token过期自动刷新
- ✅ Token获取失败处理
- ✅ 缓存过期时间验证

#### 文件上传测试
- ✅ 单文件上传成功
- ✅ **Token过期重试(字符串错误码) - Critical Issue #1**
- ✅ **Token过期重试(整数错误码) - Critical Issue #1**
- ✅ 重试次数限制
- ✅ 一般错误不重试
- ✅ 网络异常处理
- ✅ URL构建正确性
- ✅ multipart/form-data格式

### 2. 上传API测试 (test_upload_api.py)

**优先级: P1**

#### 基础功能测试
- ✅ 单文件上传成功
- ✅ 批量上传(10张)
- ✅ 缺少business_id参数
- ✅ 缺少文件参数
- ✅ 无效businessId格式
- ✅ 有效businessId格式

#### 文件验证测试
- ✅ 超出文件数量限制(>10)
- ✅ 不支持的文件类型
- ✅ 支持的文件类型(jpg/png/gif)
- ✅ 文件大小限制(10MB)

#### 高级功能测试
- ✅ 部分上传成功场景
- ✅ 上传失败重试机制(最多3次)
- ✅ 达到最大重试次数
- ✅ 数据库保存成功记录
- ✅ 数据库保存失败记录

#### 并发控制测试
- ✅ 并发上传数量限制(最多3个)

### 3. 历史查询API测试 (test_history_api.py)

**优先级: P1**

- ✅ 查询存在的记录
- ✅ 查询不存在的记录
- ✅ 返回记录字段完整性
- ✅ 记录按时间倒序排列
- ✅ 不同业务单据记录隔离
- ✅ SQL注入防护
- ✅ 成功/失败计数准确性

### 4. 数据库测试 (test_database.py)

**优先级: P1**

#### 连接测试
- ✅ 自动创建目录
- ✅ Row工厂设置

#### 初始化测试
- ✅ 创建upload_history表
- ✅ 表结构字段完整性
- ✅ 创建索引
- ✅ 重复初始化幂等性

#### 操作测试
- ✅ 插入记录
- ✅ 按business_id查询
- ✅ 索引性能验证
- ✅ 默认时间戳
- ✅ NULL值处理

### 5. 集成测试 (test_integration.py)

**优先级: P2**

#### 端到端测试
- ✅ 完整上传工作流程
- ✅ 批量上传工作流程
- ✅ 包含重试的上传流程

#### Token过期场景
- ✅ Token过期后自动刷新并重试

#### 错误处理
- ✅ 部分文件上传失败
- ✅ 网络错误处理

#### 数据持久化
- ✅ 上传历史正确保存
- ✅ 多业务单据数据隔离

#### 性能测试
- ✅ 并发上传性能验证

## 安装测试依赖

```bash
pip install -r requirements.txt
```

## 运行测试

### 运行所有测试
```bash
pytest
```

### 运行特定测试文件
```bash
# 运行用友云客户端测试
pytest tests/test_yonyou_client.py

# 运行上传API测试
pytest tests/test_upload_api.py

# 运行历史API测试
pytest tests/test_history_api.py

# 运行数据库测试
pytest tests/test_database.py

# 运行集成测试
pytest tests/test_integration.py
```

### 运行特定测试类
```bash
pytest tests/test_yonyou_client.py::TestSignatureGeneration
pytest tests/test_upload_api.py::TestUploadAPI
```

### 运行特定测试用例
```bash
# 运行Critical Issue #1相关测试
pytest tests/test_yonyou_client.py::TestFileUpload::test_upload_file_token_expired_retry_string_code
pytest tests/test_yonyou_client.py::TestFileUpload::test_upload_file_token_expired_retry_integer_code
```

### 运行带标记的测试
```bash
# 运行关键测试用例
pytest -m critical

# 运行单元测试
pytest -m unit

# 运行集成测试
pytest -m integration
```

## 测试覆盖率

### 生成覆盖率报告
```bash
# HTML报告(推荐)
pytest --cov=app --cov-report=html

# 查看HTML报告
open htmlcov/index.html
```

### 终端查看覆盖率
```bash
pytest --cov=app --cov-report=term-missing
```

### 覆盖率目标
- **核心业务逻辑**: ≥80%
- **API端点**: 100%
- **数据库操作**: ≥90%
- **整体覆盖率**: ≥70%

## 测试输出选项

### 详细输出
```bash
pytest -v
```

### 显示打印信息
```bash
pytest -s
```

### 只显示失败的测试
```bash
pytest --tb=short
```

### 停止在第一个失败
```bash
pytest -x
```

### 显示最慢的10个测试
```bash
pytest --durations=10
```

## 关键测试用例说明

### Critical Issue #1: Token过期重试机制

**问题描述**: 用友云API返回的错误码可能是字符串或整数类型,当前代码只检查字符串类型。

**测试用例**:
1. `test_upload_file_token_expired_retry_string_code` - 验证字符串错误码触发重试
2. `test_upload_file_token_expired_retry_integer_code` - 验证整数错误码触发重试(预期失败)

**位置**: `tests/test_yonyou_client.py`

**运行方式**:
```bash
pytest tests/test_yonyou_client.py::TestFileUpload::test_upload_file_token_expired_retry_string_code -v
pytest tests/test_yonyou_client.py::TestFileUpload::test_upload_file_token_expired_retry_integer_code -v
```

**修复建议**:
```python
# 修改 app/core/yonyou_client.py 第109行
# 从:
if result.get("code") == "1090003500065" and retry_count == 0:

# 改为:
if str(result.get("code")) == "1090003500065" and retry_count == 0:
```

## 测试数据说明

### 有效businessId
- "123456", "000000", "999999", "100000"

### 无效businessId
- "abc" (包含非数字)
- "12345" (长度不足)
- "1234567" (长度超过)
- "" (空字符串)

### 测试文件类型
- 支持: .jpg, .jpeg, .png, .gif
- 不支持: .txt, .pdf, .doc等

### 文件大小限制
- 最大: 10MB
- 单次最多: 10个文件

## 常见问题

### Q1: 测试运行失败怎么办?
**A**: 首先确保安装了所有测试依赖,然后检查测试输出中的错误信息。

### Q2: 如何调试单个测试?
**A**: 使用 `pytest -s tests/test_file.py::test_function` 显示打印信息进行调试。

### Q3: 覆盖率不达标怎么办?
**A**: 运行 `pytest --cov=app --cov-report=html` 查看HTML报告,找出未覆盖的代码行。

### Q4: 测试数据库冲突怎么办?
**A**: 测试使用临时数据库,每个测试独立,不会相互影响。

### Q5: 异步测试失败怎么办?
**A**: 确保使用 `@pytest.mark.asyncio` 装饰器,并安装了 `pytest-asyncio`。

## 持续集成

建议在CI/CD流程中运行以下命令:

```bash
# 安装依赖
pip install -r requirements.txt

# 运行测试并生成覆盖率报告
pytest --cov=app --cov-report=xml --cov-report=term

# 检查覆盖率阈值
pytest --cov=app --cov-fail-under=70
```

## 测试最佳实践

1. **每次提交前运行测试**: `pytest`
2. **关注覆盖率变化**: `pytest --cov=app --cov-report=term-missing`
3. **优先修复关键测试**: 运行 `pytest -m critical`
4. **保持测试快速**: 避免不必要的sleep和外部依赖
5. **使用Mock**: 所有外部API调用都应该Mock

## 联系方式

如有测试相关问题,请联系开发团队。
