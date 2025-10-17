# 需求确认文档 - 动态businessType映射

## 📋 原始需求
当前businessType为固定值，现在希望根据URL中的单据类型来确定，为销售时保持之前的，为转库或者其他时为yonbip-scm-stock

URL格式: `https://djsc.115220.xyz/?business_id=业务ID&doc_number=单据编号&doc_type=单据类型`

## 🎯 确认后的需求规格

### 功能目标
从URL参数 `doc_type` 动态确定上传到用友云时使用的 `businessType` 值，而不是使用固定值。

### 当前状态分析
- **当前实现**: `businessType` 固定为 `yonbip-scm-scmsa` (config.py:17)
- **使用位置**: YonYouClient.upload_file (yonyou_client.py:93)
- **URL格式**: 已支持 `?business_id=xxx&doc_number=xxx&doc_type=xxx`
- **字段状态**: `doc_type` 已在前后端完整实现

### 映射规则（已确认）

| doc_type值 | businessType值 | 说明 |
|-----------|---------------|------|
| **销售** | `yonbip-scm-scmsa` | 保持之前的固定值 |
| **转库** | `yonbip-scm-stock` | 新映射规则 |
| **其他** | `yonbip-scm-stock` | 新映射规则 |

### 实现范围（已确认）

1. **YonYouClient修改** (app/core/yonyou_client.py)
   - 修改 `upload_file()` 方法，接受动态 `businessType` 参数
   - 保持原有的 `self.business_type` 作为实例默认值
   - 向后兼容：如果不传参数，使用实例默认值

2. **API层修改** (app/api/upload.py)
   - 在 `/api/upload` 接口中实现映射逻辑
   - 根据 `doc_type` 映射到对应的 `businessType`
   - 传递映射后的值给 `YonYouClient.upload_file()`

3. **配置保留** (app/core/config.py)
   - 保留 `YONYOU_BUSINESS_TYPE = "yonbip-scm-scmsa"` 作为默认值
   - 用于"销售"类型和向后兼容

### 扩展策略（已确认）
- **新单据类型**: 需要在代码中显式添加映射
- **实现方式**: 使用字典映射，便于后续维护
- **默认行为**: 如果未匹配，使用配置中的默认值

### 测试策略（已确认）
- **测试方式**: 用户手动测试
- **无需自动化测试**: 跳过测试用例更新

## 🔍 需求质量评分

### 功能清晰度 (30/30分) ✅
- ✅ 清晰的输入/输出规范：doc_type → businessType 映射
- ✅ 用户交互明确：API自动映射，无需前端改动
- ✅ 成功标准：不同doc_type使用正确的businessType上传

### 技术特定性 (25/25分) ✅
- ✅ 集成点明确：YonYouClient.upload_file 和 /api/upload
- ✅ 技术约束：保持向后兼容，保留默认值
- ✅ 性能要求：无特殊要求，O(1)字典映射

### 实现完整性 (25/25分) ✅
- ✅ 边缘情况：新单据类型需要显式映射
- ✅ 错误处理：复用现有的doc_type验证逻辑
- ✅ 数据验证：doc_type已有枚举验证

### 业务上下文 (20/20分) ✅
- ✅ 用户价值：支持多种单据类型使用不同的用友云业务类型
- ✅ 优先级定义：明确的映射规则

## 📊 总质量分: 100/100分 ✅

需求已达到实现标准 (≥90分)

## 🎨 仓库上下文集成

### 遵循现有模式
- **异步架构**: 保持 async/await 模式
- **命名约定**: snake_case 函数名
- **类型提示**: 使用 Type Hints
- **错误处理**: 遵循现有的异常处理模式

### 集成点
- **核心逻辑**: app/core/yonyou_client.py (YonYouClient类)
- **API层**: app/api/upload.py (upload_files路由)
- **配置**: app/core/config.py (Settings类)

### 约束条件
- 保持向后兼容性
- 不影响现有功能
- 最小化代码改动
- 无需数据库迁移

## 📝 确认记录

### 确认轮次: 1次
- **第1轮**:
  - 提出4个澄清问题
  - 用户确认映射规则、实现范围、扩展策略、测试策略
  - 需求完全明确，达到100分

### 用户确认内容
1. ✅ 映射规则正确
2. ✅ 实现范围明确
3. ✅ 新类型需显式添加映射
4. ✅ 跳过自动化测试

## 🚀 下一步
等待用户批准进入实现阶段 (Phase 2)
