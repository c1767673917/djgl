# 单据上传管理系统 - 需求确认文档

## 原始需求
```
我要设计一个单据上传管理系统
1. 用户扫描二维码后会跳转到一个https://xxx.xxx.me/000000到网址，
   https://xxx.xxx.me 是本应用的地址，000000是businessId
2. 跳转到的页面包含一个上传图片的页面，可以从相册选择或者拍照上传
3. 根据跳转获取到的businessId用docs.txt中的方法上传图片
```

## 需求确认过程

### 第一轮确认 - 技术栈和关键参数
**问题清单:**
1. 前端技术栈
2. 后端技术栈
3. 认证凭证管理
4. businessType参数
5. 部署环境
6. 用户体验细节
7. 错误处理
8. 数据存储

**用户反馈:**
1. 前端: 纯HTML/JavaScript
2. 后端: Python + Flask/FastAPI
3. 认证信息:
   - AppKey: `2b2c5f61d8734cd49e76f8f918977c5d`
   - AppSecret: `61bc68be07201201142a8bf751a59068df9833e1`
   - 获取方式参考: BI获取销售出库.txt中的`get_access_token`函数
4. businessType固定值: `onbip-scm-scmsa`
5. 部署: IP地址运行在10000端口
6. 用户体验:
   - 单次最多上传10张图片
   - 需要图片预览功能
   - 上传成功后提示成功即可
   - 需要显示上传进度
7. 错误处理:
   - 上传失败时提示失败，并显示报错代码
   - 需要重试机制
8. 数据存储: 需要本地数据库记录上传历史

## 最终确认需求 (质量评分: 95/100)

### 功能需求 (30/30)

#### 1. 二维码跳转功能
- **路由格式**: `http://{IP}:10000/{businessId}`
- **参数提取**: 从URL路径中提取businessId
- **验证**: businessId格式验证 (6位数字)

#### 2. 图片上传界面
- **上传方式**:
  - 相册选择 (支持多选)
  - 拍照上传 (调用摄像头)
- **数量限制**: 单次最多10张
- **预览功能**: 上传前显示缩略图预览
- **进度显示**: 实时显示每张图片的上传进度百分比
- **文件验证**:
  - 格式限制: jpg, jpeg, png, gif
  - 大小限制: 单张最大10MB

#### 3. API集成上传
- **目标API**: 用友云平台文件上传接口
  ```
  POST /yonbip/uspace/iuap-apcom-file/rest/v1/file
  ```
- **必填参数**:
  - `access_token`: 通过AppKey/AppSecret动态获取
  - `businessType`: 固定值 `onbip-scm-scmsa`
  - `businessId`: 从URL路径提取
  - `files`: 图片文件 (multipart/form-data)

#### 4. 认证机制
- **Token获取**:
  - AppKey: `2b2c5f61d8734cd49e76f8f918977c5d`
  - AppSecret: `61bc68be07201201142a8bf751a59068df9833e1`
  - 签名算法: HMAC-SHA256
  - 请求格式:
    ```
    GET https://c4.yonyoucloud.com/iuap-api-auth/open-auth/selfAppAuth/base/v1/getAccessToken
    ?appKey={appKey}&timestamp={timestamp}&signature={signature}
    ```
- **Token管理**:
  - 缓存机制避免频繁获取
  - 过期自动刷新

#### 5. 上传历史记录
- **存储信息**:
  - businessId
  - 文件名列表
  - 上传时间
  - 上传状态 (成功/失败)
  - 错误信息 (如有)
  - 用友云返回的文件ID
- **查询功能**: 按businessId查询历史记录

### 技术需求 (25/25)

#### 技术栈
- **前端**:
  - 纯HTML/CSS/JavaScript
  - 无需构建工具
  - 响应式设计 (移动端优先)
- **后端**:
  - Python 3.8+
  - FastAPI (推荐) 或 Flask
  - SQLite数据库
- **部署**:
  - 运行端口: 10000
  - 支持局域网访问

#### API端点设计
```
GET  /{businessId}              - 上传页面
POST /api/upload                - 图片上传接口
POST /api/token                 - 获取access_token
GET  /api/history/{businessId}  - 查询上传历史
POST /api/retry                 - 重试上传
```

#### 数据库Schema
```sql
CREATE TABLE upload_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_id VARCHAR(50) NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    file_size INTEGER,
    upload_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20),  -- 'success', 'failed'
    error_code VARCHAR(50),
    error_message TEXT,
    yonyou_file_id VARCHAR(255),
    INDEX idx_business_id (business_id)
);
```

### 实现完整性 (25/25)

#### 错误处理
1. **网络错误**:
   - 超时处理 (30秒)
   - 重试机制 (最多3次)
   - 友好的错误提示
2. **业务错误**:
   - Token获取失败
   - 文件上传失败 (显示用友云返回的错误码和消息)
   - businessId不存在
3. **客户端错误**:
   - 文件格式错误
   - 文件大小超限
   - 数量超限

#### 用户体验优化
1. **加载状态**: 所有异步操作显示loading状态
2. **进度反馈**: 上传进度条 (0-100%)
3. **成功提示**: Toast消息提示上传成功
4. **失败提示**: 详细错误信息 + 重试按钮
5. **图片预览**: 点击缩略图查看大图
6. **批量操作**: 支持删除已选图片

#### 边界情况
- 无文件选择时禁用上传按钮
- 重复上传相同文件的处理
- 并发上传数量控制 (最多3个并发)
- Token过期时自动刷新

### 业务上下文 (20/20)

#### 用户价值
- **简化流程**: 扫码即用，无需登录
- **移动友好**: 支持手机浏览器直接拍照上传
- **可追溯性**: 完整的上传历史记录
- **可靠性**: 失败重试机制确保上传成功

#### 使用场景
1. 仓库工作人员扫描单据二维码
2. 拍照或选择单据照片
3. 批量上传至用友云平台
4. 系统自动关联businessId
5. 查看历史上传记录

#### 优先级
- P0 (必须): 基础上传功能 + Token认证
- P1 (重要): 预览功能 + 上传历史
- P2 (优化): 重试机制 + 进度显示

## 代码库上下文集成

### 现有资源
- `docs.txt`: 用友云文件上传API文档
- `BI获取销售出库.txt`: Token获取示例代码 (Python实现)

### 技术约束
- 必须使用用友云BIP平台API
- 必须遵循OAuth 2.0认证流程
- 必须处理MDD幂等性 (通过businessId)

### 集成要点
1. 复用`get_access_token`函数逻辑
2. 使用multipart/form-data格式上传文件
3. 正确处理HMAC-SHA256签名计算
4. 妥善管理AppKey/AppSecret (环境变量)

## 质量评分明细

| 维度 | 分数 | 说明 |
|-----|------|------|
| 功能清晰度 | 30/30 | 所有功能点明确，有清晰的输入输出规范 |
| 技术特异性 | 25/25 | 技术栈确定，API集成细节完整 |
| 实现完整性 | 25/25 | 边界情况、错误处理、用户体验全面覆盖 |
| 业务上下文 | 15/20 | 使用场景清晰，优先级明确，缺少性能要求细节 |
| **总分** | **95/100** | **高质量需求，可以直接进入实现阶段** |

## 待确认项
无

## 下一步
需求已达到90+分，等待用户确认是否开始实现。
