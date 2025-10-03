# 仓库上下文分析报告

## 执行摘要

**项目名称**: 单据上传管理系统
**项目类型**: Web应用 (FastAPI + 用友云API集成)
**主要语言**: Python 3.8+
**代码规模**: ~3097行代码
**最后更新**: 2025-10-03

本系统是一个轻量级的单据图片上传管理平台,集成用友云API,支持移动端扫码上传、批量文件处理、历史记录管理和后台管理功能。

---

## 1. 项目结构分析

### 1.1 项目类型
- **应用类型**: Web应用(前后端混合架构)
- **主要功能**:
  - 移动端图片上传
  - 用友云API文件管理
  - 上传历史记录查询
  - 后台管理系统

### 1.2 目录结构

```
单据上传管理/
├── app/                          # 主应用目录
│   ├── __init__.py
│   ├── main.py                   # FastAPI应用入口
│   ├── api/                      # API路由模块
│   │   ├── __init__.py
│   │   ├── upload.py             # 上传API (文件上传、重命名、本地存储)
│   │   ├── history.py            # 历史记录API (按业务ID查询)
│   │   └── admin.py              # 管理API (分页查询、导出、统计)
│   ├── core/                     # 核心模块
│   │   ├── __init__.py
│   │   ├── config.py             # 配置管理 (Pydantic Settings)
│   │   ├── database.py           # 数据库操作 (SQLite)
│   │   └── yonyou_client.py      # 用友云API客户端 (HMAC-SHA256签名)
│   ├── models/                   # 数据模型
│   │   ├── __init__.py
│   │   └── upload_history.py     # 上传历史模型
│   └── static/                   # 前端静态文件
│       ├── index.html            # 上传页面
│       ├── admin.html            # 管理页面
│       ├── css/
│       │   ├── style.css         # 上传页面样式
│       │   └── admin.css         # 管理页面样式
│       └── js/
│           ├── app.js            # 上传页面逻辑 (二维码识别、并发上传)
│           └── admin.js          # 管理页面逻辑 (分页、筛选、导出)
├── data/                         # 数据目录
│   ├── uploads.db                # SQLite数据库
│   └── uploaded_files/           # 本地文件存储
├── tests/                        # 测试目录
│   ├── conftest.py               # Pytest配置和fixtures
│   ├── test_upload_api.py        # 上传API测试
│   ├── test_history_api.py       # 历史API测试
│   ├── test_database.py          # 数据库测试
│   ├── test_yonyou_client.py     # 用友云客户端测试
│   ├── test_integration.py       # 集成测试
│   ├── fixtures/                 # 测试数据
│   └── reports/                  # 测试报告
├── logs/                         # 日志目录
├── .env                          # 环境变量配置
├── requirements.txt              # Python依赖
├── run.py                        # 启动脚本
├── pytest.ini                    # Pytest配置
└── README.md                     # 项目文档
```

### 1.3 架构特点
- **三层架构**: API层(路由) → 核心层(业务逻辑) → 数据层(数据库)
- **模块化设计**: 清晰的职责分离
- **前后端分离**: 静态HTML + RESTful API
- **异步处理**: FastAPI异步框架 + httpx异步HTTP客户端

---

## 2. 技术栈发现

### 2.1 后端技术栈

#### 核心框架
- **FastAPI 0.104.1**: 现代化Python Web框架
- **Uvicorn 0.24.0**: ASGI服务器 (支持热重载)
- **Pydantic 2.5.0**: 数据验证和配置管理
- **httpx 0.25.1**: 异步HTTP客户端

#### 数据存储
- **SQLite 3**: 轻量级嵌入式数据库
- **本地文件系统**: 图片文件存储 (data/uploaded_files/)

#### 文件处理
- **python-multipart 0.0.6**: multipart/form-data解析
- **Pillow 10.1.0**: 图像处理 (测试用)

#### 配置管理
- **pydantic-settings 2.1.0**: 环境变量配置
- **python-dotenv 1.0.0**: .env文件加载

### 2.2 前端技术栈

#### 基础技术
- **原生HTML5**: 语义化标签
- **原生CSS3**: 响应式设计、Flexbox/Grid布局
- **原生JavaScript (ES6+)**: 异步操作、Promise、async/await

#### 第三方库
- **jsQR 1.4.0**: 二维码识别库 (CDN引入)

#### 前端特性
- 移动端优先设计
- 触摸友好交互
- 实时进度反馈
- 图片预览功能
- 并发控制 (最多3个并发上传)

### 2.3 测试框架

#### 测试工具
- **pytest 7.4.3**: 测试框架
- **pytest-asyncio 0.21.1**: 异步测试支持
- **pytest-cov 4.1.0**: 覆盖率测试
- **pytest-mock 3.12.0**: Mock支持

#### 测试策略
- 单元测试 (数据库、API、客户端)
- 集成测试 (端到端流程)
- 代码覆盖率要求: ≥70%
- 测试标记: unit, integration, slow, critical

### 2.4 外部API集成

#### 用友云API
- **认证方式**: HMAC-SHA256签名算法
- **Token管理**: 自动缓存和刷新 (1小时有效期)
- **文件上传**: multipart/form-data格式
- **API端点**:
  - 认证: `https://c4.yonyoucloud.com/iuap-api-auth/.../getAccessToken`
  - 上传: `https://c4.yonyoucloud.com/iuap-api-gateway/.../file`

---

## 3. 代码模式分析

### 3.1 编码标准和约定

#### Python代码规范
- 遵循PEP 8风格指南
- 类型注解 (Type Hints): `Dict[str, Any]`, `Optional[str]`
- 异步编程: `async def`, `await`
- 上下文管理器: `async with`, `with`

#### 命名约定
- **文件名**: snake_case (例: `upload_history.py`)
- **类名**: PascalCase (例: `YonYouClient`, `UploadHistory`)
- **函数/变量**: snake_case (例: `get_access_token`, `business_id`)
- **常量**: UPPER_SNAKE_CASE (例: `MAX_FILE_SIZE`)

#### 文档字符串
- 函数文档: 三引号字符串 + 参数说明 + 返回值说明
- API端点: 包含请求/响应格式示例

### 3.2 设计模式

#### 1. 单例模式 (Singleton)
```python
# app/core/config.py
@lru_cache()
def get_settings():
    return Settings()
```
配置对象全局唯一,使用`lru_cache`实现缓存。

#### 2. 工厂模式 (Factory)
```python
# app/core/database.py
def get_db_connection():
    """获取数据库连接"""
    db_path = settings.DATABASE_URL.replace("sqlite:///", "")
    conn = sqlite3.connect(db_path)
    return conn
```
数据库连接创建集中管理。

#### 3. 客户端封装模式 (Client Wrapper)
```python
# app/core/yonyou_client.py
class YonYouClient:
    """封装用友云API调用"""
    async def get_access_token(self):
        ...
    async def upload_file(self):
        ...
```
封装外部API调用,隐藏复杂的认证和签名逻辑。

#### 4. 重试模式 (Retry Pattern)
```python
# app/api/upload.py
for attempt in range(settings.MAX_RETRY_COUNT):
    result = await yonyou_client.upload_file(...)
    if result["success"]:
        break
    elif attempt < settings.MAX_RETRY_COUNT - 1:
        await asyncio.sleep(settings.RETRY_DELAY)
```
文件上传失败自动重试(最多3次)。

#### 5. 并发控制模式 (Semaphore)
```python
# app/api/upload.py
semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_UPLOADS)
async def upload_single_file(upload_file: UploadFile):
    async with semaphore:
        ...
```
限制同时上传文件数量(最多3个)。

### 3.3 组件组织

#### API路由组织
- 按功能模块拆分: `upload.py`, `history.py`, `admin.py`
- 使用APIRouter实现模块化路由
- 统一的错误处理: HTTPException

#### 数据库操作
- 无ORM框架,直接使用sqlite3
- 手动管理连接和事务
- 索引优化: business_id, upload_time, status, doc_number, doc_type

#### 前端组织
- 页面级拆分: index.html (上传), admin.html (管理)
- CSS模块化: style.css, admin.css
- JavaScript模块化: app.js, admin.js
- 无前端构建工具 (原生开发)

---

## 4. API结构和端点

### 4.1 页面路由

| 路由 | 方法 | 说明 |
|------|------|------|
| `GET /` | GET | 上传页面入口 (需传business_id, doc_number, doc_type参数) |
| `GET /admin` | GET | 管理页面入口 |

### 4.2 上传API (`/api/upload`)

| 端点 | 方法 | 说明 |
|------|------|------|
| `POST /api/upload` | POST | 批量上传文件到用友云 |

**请求参数**:
- `business_id`: 业务单据ID (纯数字,用于用友云API)
- `doc_number`: 单据编号 (业务标识,如SO20250103001)
- `doc_type`: 单据类型 (销售/转库/其他)
- `files`: 文件列表 (最多10个,单个最大10MB)

**响应格式**:
```json
{
  "success": true,
  "total": 10,
  "succeeded": 9,
  "failed": 1,
  "results": [...]
}
```

### 4.3 历史记录API (`/api/history`)

| 端点 | 方法 | 说明 |
|------|------|------|
| `GET /api/history/{business_id}` | GET | 查询指定业务单据的上传历史 |

**响应格式**:
```json
{
  "business_id": "123456",
  "total_count": 15,
  "success_count": 14,
  "failed_count": 1,
  "records": [...]
}
```

### 4.4 管理API (`/api/admin`)

| 端点 | 方法 | 说明 |
|------|------|------|
| `GET /api/admin/records` | GET | 获取上传记录列表 (分页、筛选) |
| `GET /api/admin/export` | GET | 导出上传记录为ZIP包 (Excel + 图片) |
| `GET /api/admin/statistics` | GET | 获取统计数据 |

**分页和筛选参数**:
- `page`: 页码 (默认1)
- `page_size`: 每页记录数 (默认20,最大100)
- `search`: 搜索关键词 (模糊匹配单据编号或文件名)
- `doc_type`: 单据类型筛选 (销售/转库/其他)
- `start_date`: 开始日期 (YYYY-MM-DD)
- `end_date`: 结束日期 (YYYY-MM-DD)

---

## 5. 数据库架构

### 5.1 数据表结构

#### upload_history表
```sql
CREATE TABLE upload_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_id VARCHAR(50) NOT NULL,       -- 用友云业务ID
    doc_number VARCHAR(100),                -- 单据编号 (新增字段)
    doc_type VARCHAR(20),                   -- 单据类型 (销售/转库/其他)
    file_name VARCHAR(255) NOT NULL,        -- 文件名
    file_size INTEGER NOT NULL,             -- 文件大小(字节)
    file_extension VARCHAR(20),             -- 文件扩展名
    upload_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) NOT NULL,            -- 状态: success/failed
    error_code VARCHAR(50),                 -- 错误码
    error_message TEXT,                     -- 错误信息
    yonyou_file_id VARCHAR(255),            -- 用友云文件ID
    retry_count INTEGER DEFAULT 0,          -- 重试次数
    local_file_path VARCHAR(500),           -- 本地文件路径 (新增)
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### 5.2 索引设计
```sql
CREATE INDEX idx_business_id ON upload_history(business_id);
CREATE INDEX idx_upload_time ON upload_history(upload_time);
CREATE INDEX idx_status ON upload_history(status);
CREATE INDEX idx_doc_number ON upload_history(doc_number);
CREATE INDEX idx_doc_type ON upload_history(doc_type);
CREATE INDEX idx_doc_type_upload_time ON upload_history(doc_type, upload_time);
```

### 5.3 数据库迁移
- 使用ALTER TABLE动态添加新字段 (兼容旧版本数据库)
- 字段兼容性检查: `PRAGMA table_info(upload_history)`
- 无专用迁移工具,通过代码实现增量升级

---

## 6. 开发工作流

### 6.1 Git工作流

#### 分支策略
- **主分支**: `main` (生产分支)
- **远程仓库**: `origin/main`
- **提交历史** (最近5次):
  1. `c97cbfa` - 后台管理
  2. `0d7298c` - 修复token认证
  3. `f340c8e` - 二维码验证
  4. `f7a989f` - 删除无用文件
  5. `9460a51` - 解决bug

#### 提交规范
- 简洁的中文提交信息
- 按功能点提交 (如"后台管理"、"修复token认证")

### 6.2 CI/CD管道
- **当前状态**: 无CI/CD配置
- **建议**: 可考虑添加GitHub Actions或GitLab CI

### 6.3 测试策略

#### 测试命令
```bash
pytest                              # 运行所有测试
pytest --cov=app                    # 代码覆盖率测试
pytest -m unit                      # 只运行单元测试
pytest -m integration               # 只运行集成测试
pytest -v --tb=short                # 详细输出
```

#### 测试覆盖率
- **要求**: ≥70%
- **报告**: HTML格式 (htmlcov/)

#### 测试文件
- `test_database.py`: 数据库操作测试
- `test_upload_api.py`: 上传API测试
- `test_history_api.py`: 历史API测试
- `test_yonyou_client.py`: 用友云客户端测试
- `test_integration.py`: 集成测试

### 6.4 部署配置

#### 启动方式
```bash
# 方式1: 使用run.py (推荐)
python run.py

# 方式2: 直接使用uvicorn
uvicorn app.main:app --host 0.0.0.0 --port 10000 --reload
```

#### 后台运行 (Linux/macOS)
```bash
# 使用nohup
nohup python run.py > logs/app.log 2>&1 &

# 查看进程
ps aux | grep python

# 停止服务
kill <PID>
```

#### 生产环境建议
- 使用systemd服务 (Linux)
- 配置HTTPS (Nginx反向代理)
- 限制CORS域名
- 定期备份数据库

---

## 7. 核心功能模块

### 7.1 文件上传流程

1. **前端选择文件** → 本地预览
2. **发起上传请求** → `/api/upload` (POST)
3. **后端验证**:
   - business_id格式 (纯数字)
   - doc_type枚举值 (销售/转库/其他)
   - 文件数量 (最多10个)
   - 文件大小 (最大10MB)
   - 文件格式 (jpg/jpeg/png/gif)
4. **文件重命名**: 基于doc_number生成唯一文件名 (如`SO20250103001.jpg`, `SO20250103001-1.jpg`)
5. **并发上传** (最多3个并发):
   - 上传到用友云API
   - 失败自动重试 (最多3次)
   - Token过期自动刷新
6. **本地存储**: 上传成功后保存到`data/uploaded_files/`
7. **数据库记录**: 保存上传历史到SQLite
8. **返回结果**: 统计成功/失败数量

### 7.2 Token管理机制

#### 认证流程
1. 生成时间戳 (毫秒)
2. 构建签名字符串: `appKey{appKey}timestamp{timestamp}`
3. HMAC-SHA256签名: `hmac(app_secret, string_to_sign)`
4. Base64编码 + URL编码
5. 发送GET请求: `{auth_url}?appKey={key}&timestamp={ts}&signature={sig}`

#### Token缓存
- **缓存时长**: 1小时 (提前60秒过期)
- **缓存位置**: 内存 (`YonYouClient._token_cache`)
- **刷新策略**: 检测到Token过期错误码 (1090003500065, 310036) 时自动刷新

### 7.3 后台管理功能

#### 记录查询
- 分页显示 (默认20条/页,最大100条/页)
- 多条件筛选: 搜索关键词、单据类型、日期范围
- 只显示成功记录 (`status='success'`)
- 排序: 按上传时间倒序

#### 数据导出
- 导出格式: ZIP包 (包含Excel表格 + 所有图片文件)
- Excel内容: 单据编号、单据类型、业务ID、上传时间、文件名、文件大小
- 图片组织: ZIP内`images/`目录

#### 统计数据
- 总上传数、成功数、失败数
- 按单据类型统计 (销售、转库、其他)

### 7.4 二维码上传功能

#### 实现方式
- **库**: jsQR 1.4.0
- **触发**: 上传页面支持通过二维码快速访问
- **URL格式**: `http://{IP}:{PORT}/?business_id={id}&doc_number={num}&doc_type={type}`

---

## 8. 配置管理

### 8.1 环境变量 (.env)

#### 应用配置
- `APP_NAME`: 应用名称
- `HOST`: 监听地址 (默认0.0.0.0)
- `PORT`: 监听端口 (默认10000)
- `DEBUG`: 调试模式 (默认false)

#### 用友云配置
- `YONYOU_APP_KEY`: 应用Key
- `YONYOU_APP_SECRET`: 应用Secret
- `YONYOU_BUSINESS_TYPE`: 业务类型 (yonbip-scm-scmsa)
- `YONYOU_AUTH_URL`: 认证API地址
- `YONYOU_UPLOAD_URL`: 上传API地址

#### 上传限制
- `MAX_FILE_SIZE`: 单文件最大大小 (10MB)
- `MAX_FILES_PER_REQUEST`: 单次最多文件数 (10个)
- `ALLOWED_EXTENSIONS`: 允许的文件扩展名 (jpg/jpeg/png/gif)

#### 重试配置
- `MAX_RETRY_COUNT`: 最大重试次数 (3次)
- `RETRY_DELAY`: 重试间隔 (2秒)
- `REQUEST_TIMEOUT`: 请求超时时间 (30秒)

#### 并发控制
- `MAX_CONCURRENT_UPLOADS`: 最大并发上传数 (3个)

#### 数据库配置
- `DATABASE_URL`: 数据库路径 (sqlite:///data/uploads.db)
- `LOCAL_STORAGE_PATH`: 本地文件存储路径 (data/uploaded_files)

#### Token配置
- `TOKEN_CACHE_DURATION`: Token缓存时长 (3600秒)

### 8.2 配置加载机制
- 使用`pydantic-settings`实现配置管理
- 支持环境变量覆盖.env文件
- 配置验证: 类型检查、默认值
- 全局单例: `get_settings()`使用`lru_cache`缓存

---

## 9. 新功能集成点

### 9.1 添加删除按钮到管理页面

#### 推荐集成位置
1. **后端API**: `app/api/admin.py`
   - 添加新端点: `DELETE /api/admin/records/{id}` 或 `DELETE /api/admin/records` (批量)
   - 删除逻辑:
     - 从数据库删除记录
     - 删除本地文件 (`local_file_path`)
     - (可选) 从用友云删除文件

2. **前端页面**: `app/static/admin.html`
   - 在表格每行添加删除按钮 (或复选框 + 批量删除按钮)
   - 添加确认对话框

3. **前端逻辑**: `app/static/js/admin.js`
   - 实现删除功能的API调用
   - 刷新表格数据

#### 集成注意事项
- **权限控制**: 当前无认证机制,建议添加管理员认证
- **软删除 vs 硬删除**: 建议使用软删除 (添加`deleted_at`字段)
- **日志记录**: 记录删除操作的用户和时间
- **批量操作**: 支持批量删除以提高效率

### 9.2 其他可能的扩展点

#### 1. 认证与授权
- 当前位置: 可在`app/api/admin.py`添加认证中间件
- 建议方案: JWT Token认证 或 OAuth2

#### 2. 文件预览
- 当前位置: `app/static/admin.html`
- 实现方案: 添加预览模态框,显示本地存储的图片

#### 3. 文件下载
- 当前位置: `app/api/admin.py`
- 实现方案: 添加`GET /api/admin/download/{id}`端点

#### 4. 审计日志
- 当前位置: `app/core/database.py`
- 实现方案: 创建`audit_log`表记录所有操作

#### 5. 高级筛选
- 当前位置: `app/static/admin.html`和`app/static/js/admin.js`
- 实现方案: 添加更多筛选条件 (文件大小范围、状态等)

---

## 10. 潜在约束和考虑因素

### 10.1 技术约束

#### 性能限制
- **数据库**: SQLite不适合高并发写入场景 (建议并发数<100)
- **文件存储**: 本地文件系统存储,单机容量有限
- **并发控制**: 前端限制3个并发上传,后端无并发限制

#### 扩展性限制
- **水平扩展**: 单机部署,无分布式支持
- **数据迁移**: SQLite不适合大规模数据 (建议<1GB)
- **缓存**: Token缓存在内存中,重启后丢失

### 10.2 安全考虑

#### 当前安全措施
- CORS允许所有域名 (`allow_origins=["*"]`) - **生产环境需限制**
- 无用户认证机制 - **管理页面建议添加认证**
- 文件类型验证 (只允许图片格式)
- 文件大小限制 (10MB)

#### 建议的安全改进
1. **添加管理员认证**: JWT Token或OAuth2
2. **限制CORS域名**: 只允许可信域名
3. **API速率限制**: 防止滥用
4. **敏感信息保护**: .env文件不提交到Git (已配置)
5. **SQL注入防护**: 使用参数化查询 (已实现)

### 10.3 运维考虑

#### 日志管理
- 当前日志输出到控制台
- 建议: 使用日志轮转 (logrotate) 或日志服务 (如Sentry)

#### 数据备份
- 当前无自动备份机制
- 建议: 定期备份`data/uploads.db`和`data/uploaded_files/`

#### 监控告警
- 当前无监控系统
- 建议: 添加健康检查端点 (`GET /health`) 和监控工具 (如Prometheus)

### 10.4 业务约束

#### 用友云API限制
- Token有效期: 1小时
- 上传文件大小: 受用友云API限制
- API速率限制: 未知 (需查阅用友云文档)

#### 业务规则
- 单据类型: 仅支持"销售"、"转库"、"其他"三种
- 文件命名: 基于doc_number生成,重复自动加流水号
- 重试策略: 最多3次,间隔2秒

---

## 11. 文档资源

### 11.1 项目文档
- `README.md`: 完整的项目文档 (安装、配置、使用、故障排查)
- `tests/README_TESTING.md`: 测试文档
- `tests/QUICK_START.md`: 快速开始指南
- `tests/TEST_SUMMARY.md`: 测试摘要
- `tests/TEST_REPORT.md`: 测试报告

### 11.2 API文档
- Swagger UI: `http://localhost:10000/docs`
- ReDoc: `http://localhost:10000/redoc`

### 11.3 代码注释
- 所有API端点包含详细文档字符串
- 核心函数包含参数和返回值说明
- 复杂逻辑包含行内注释

---

## 12. 开发规范建议

### 12.1 代码风格
- 遵循PEP 8
- 使用类型注解
- 函数单一职责原则
- 避免深层嵌套 (最多3层)

### 12.2 错误处理
- 使用HTTPException抛出HTTP错误
- 记录详细的错误日志
- 返回友好的错误信息

### 12.3 测试规范
- 每个新功能必须包含单元测试
- 保持代码覆盖率≥70%
- 使用Mock隔离外部依赖
- 集成测试验证端到端流程

### 12.4 版本控制
- 提交前运行测试: `pytest`
- 提交信息清晰描述改动
- 大功能分支开发,合并前Code Review

---

## 13. 总结

### 13.1 项目优势
✅ 架构清晰,模块化设计
✅ 异步处理,性能良好
✅ 完善的测试覆盖
✅ 详细的文档和注释
✅ 移动端友好的用户界面
✅ 自动重试和Token管理机制
✅ 本地文件存储备份

### 13.2 改进建议
⚠️ 添加管理员认证机制
⚠️ 限制CORS域名
⚠️ 实现软删除功能
⚠️ 添加API速率限制
⚠️ 迁移到PostgreSQL (高并发场景)
⚠️ 添加监控和告警
⚠️ 配置CI/CD管道

### 13.3 新功能开发指南 (删除按钮)

**步骤1**: 添加后端API (`app/api/admin.py`)
```python
@router.delete("/records/{record_id}")
async def delete_record(record_id: int):
    """删除单条记录"""
    # 1. 查询记录获取local_file_path
    # 2. 删除数据库记录
    # 3. 删除本地文件
    # 4. 返回结果
```

**步骤2**: 修改前端页面 (`app/static/admin.html`)
```html
<td>
    <button class="btn-delete" data-id="{{record.id}}">删除</button>
</td>
```

**步骤3**: 实现前端逻辑 (`app/static/js/admin.js`)
```javascript
// 删除按钮点击事件
document.addEventListener('click', async (e) => {
    if (e.target.classList.contains('btn-delete')) {
        const id = e.target.dataset.id;
        if (confirm('确认删除该记录?')) {
            const response = await fetch(`/api/admin/records/${id}`, {
                method: 'DELETE'
            });
            if (response.ok) {
                loadRecords(); // 刷新列表
            }
        }
    }
});
```

**步骤4**: 添加测试 (`tests/test_admin_api.py`)
```python
async def test_delete_record_success():
    """测试删除记录成功"""
    # 实现测试逻辑
```

---

## 附录: 文件清单

### Python文件 (12个)
- `run.py`
- `app/__init__.py`
- `app/main.py`
- `app/core/__init__.py`
- `app/core/config.py`
- `app/core/database.py`
- `app/core/yonyou_client.py`
- `app/models/__init__.py`
- `app/models/upload_history.py`
- `app/api/__init__.py`
- `app/api/upload.py`
- `app/api/history.py`
- `app/api/admin.py`

### 测试文件 (6个)
- `tests/conftest.py`
- `tests/test_database.py`
- `tests/test_upload_api.py`
- `tests/test_history_api.py`
- `tests/test_yonyou_client.py`
- `tests/test_integration.py`

### 前端文件 (6个)
- `app/static/index.html`
- `app/static/admin.html`
- `app/static/css/style.css`
- `app/static/css/admin.css`
- `app/static/js/app.js`
- `app/static/js/admin.js`

### 配置文件 (4个)
- `.env`
- `requirements.txt`
- `pytest.ini`
- `.gitignore`

### 文档文件 (5个)
- `README.md`
- `tests/README_TESTING.md`
- `tests/QUICK_START.md`
- `tests/TEST_SUMMARY.md`
- `tests/TEST_REPORT.md`

---

**报告生成时间**: 2025-10-03
**分析工具**: Claude Code AI Assistant
**版本**: 1.0.0
