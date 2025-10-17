# 仓库上下文报告

生成日期: 2025-10-17
仓库路径: `/Users/lichuansong/Desktop/projects/单据上传管理`

---

## 1. 项目概述

### 1.1 项目类型与目的

**项目名称**: 单据上传管理系统

**项目类型**: Web应用 - 企业内部工具

**核心目的**:
- 为用友云平台提供移动端友好的单据图片上传功能
- 通过二维码扫描快速访问特定单据的上传页面
- 支持批量上传、历史记录查询、后台管理等功能
- 提供完整的上传历史追踪和数据导出能力

**业务场景**:
- 移动端扫码上传单据照片到用友云
- 支持销售单、转库单等不同类型单据
- 本地备份上传文件，支持离线查询
- 管理员可查看统计、导出数据、删除记录

### 1.2 最近开发历史

根据Git提交记录，最近的开发重点包括：
- jsQR本地化 (094c4a2)
- Docker部署支持 (438663d)
- 时区问题修复 (effe1e5, 72ac12c)
- 环境变量优化 (fd09718)
- 后台管理功能 (c97cbfa)
- 删除功能 (09767d8)
- Token认证修复 (0d7298c)

---

## 2. 技术栈分析

### 2.1 后端技术栈

#### 核心框架
- **FastAPI 0.104.1**: 现代化的Python异步Web框架
- **Uvicorn 0.24.0**: ASGI服务器，支持异步处理

#### 主要依赖
- **httpx 0.25.1**: 异步HTTP客户端（用于调用用友云API）
- **Pydantic 2.5.0**: 数据验证和设置管理
- **pydantic-settings 2.1.0**: 环境变量配置管理
- **python-multipart 0.0.6**: 文件上传处理
- **python-dotenv 1.0.0**: 环境变量加载
- **openpyxl 3.1.2**: Excel文件生成（用于数据导出）

#### 测试框架
- **pytest 7.4.3**: 测试框架
- **pytest-asyncio 0.21.1**: 异步测试支持
- **pytest-cov 4.1.0**: 代码覆盖率
- **pytest-mock 3.12.0**: Mock测试
- **Pillow 10.1.0**: 图片处理测试

#### 数据库
- **SQLite**: 轻量级关系数据库
- 数据库文件路径: `data/uploads.db`
- 支持软删除、时间索引、类型筛选等功能

### 2.2 前端技术栈

#### 技术选择
- **原生HTML/CSS/JavaScript**: 无框架依赖，轻量级
- **jsQR.min.js**: 二维码识别库（已本地化）
- **响应式设计**: 移动端优先

#### 前端文件结构
- `/app/static/index.html`: 主上传页面
- `/app/static/admin.html`: 后台管理页面
- `/app/static/css/style.css`: 主样式表
- `/app/static/css/admin.css`: 管理页面样式
- `/app/static/js/app.js`: 上传逻辑 (674行)
- `/app/static/js/admin.js`: 管理逻辑
- `/app/static/js/jsQR.min.js`: 二维码库（本地化）

### 2.3 部署技术栈

#### Docker支持
- **Dockerfile**: 基于Python 3.9-slim
- **docker-compose.yml**: 容器编排配置
- 健康检查配置
- 数据卷持久化

#### 运行环境
- Python 3.8+
- 端口: 10000 (默认)
- 支持本地运行和Docker容器化部署

---

## 3. 代码组织模式

### 3.1 项目结构

```
单据上传管理/
├── app/                          # 应用主目录
│   ├── __init__.py
│   ├── main.py                   # FastAPI应用入口
│   ├── api/                      # API路由层
│   │   ├── __init__.py
│   │   ├── upload.py             # 上传API (259行)
│   │   ├── history.py            # 历史记录API (78行)
│   │   └── admin.py              # 管理API (347行)
│   ├── core/                     # 核心业务逻辑
│   │   ├── __init__.py
│   │   ├── config.py             # 配置管理 (66行)
│   │   ├── database.py           # 数据库操作 (98行)
│   │   ├── yonyou_client.py      # 用友云API客户端 (131行)
│   │   └── timezone.py           # 时区工具 (64行)
│   ├── models/                   # 数据模型
│   │   ├── __init__.py
│   │   └── upload_history.py    # 上传历史模型 (38行)
│   └── static/                   # 静态文件
│       ├── index.html            # 上传页面
│       ├── admin.html            # 管理页面
│       ├── css/                  # 样式文件
│       └── js/                   # JavaScript文件
├── tests/                        # 测试目录 (2915行)
│   ├── conftest.py              # 测试配置
│   ├── test_*.py                # 各模块测试
│   └── fixtures/                # 测试数据
├── data/                        # 数据目录（自动创建）
│   ├── uploads.db               # SQLite数据库
│   └── uploaded_files/          # 本地文件存储
├── logs/                        # 日志目录
├── .env                         # 环境变量配置
├── .env.example                 # 环境变量示例
├── requirements.txt             # Python依赖
├── run.py                       # 启动脚本
├── pytest.ini                   # 测试配置
├── Dockerfile                   # Docker镜像配置
├── docker-compose.yml           # Docker编排配置
├── .dockerignore                # Docker忽略文件
├── README.md                    # 项目文档
└── DOCKER_DEPLOYMENT.md         # Docker部署文档
```

**代码量统计**:
- 应用代码: ~1,156行Python代码
- 测试代码: ~2,915行测试代码
- 测试覆盖率要求: ≥70%

### 3.2 架构模式

#### 分层架构
1. **表现层 (Presentation Layer)**
   - 静态HTML页面
   - REST API端点（FastAPI路由）

2. **业务逻辑层 (Business Logic Layer)**
   - `app/api/`: API路由和请求处理
   - `app/core/`: 核心业务逻辑
   - `app/models/`: 数据模型

3. **数据访问层 (Data Access Layer)**
   - `app/core/database.py`: SQLite数据库操作
   - `app/core/yonyou_client.py`: 外部API调用

#### 关键设计模式

**1. 配置管理模式**
- 使用 `pydantic-settings` 管理配置
- 环境变量优先，支持 `.env` 文件
- 启动时验证必需配置（AppKey, AppSecret）

**2. 客户端模式**
- `YonYouClient`: 封装用友云API交互
- Token自动缓存和刷新机制
- HMAC-SHA256签名算法

**3. 数据访问模式**
- 直接使用SQLite连接（轻量级场景）
- 连接工厂: `get_db_connection()`
- 软删除策略（`deleted_at`字段）

**4. 时区处理模式**
- 统一使用北京时间（UTC+8）
- `timezone.py` 提供时区工具函数
- 数据库存储naive datetime

---

## 4. API架构

### 4.1 API端点设计

#### 上传相关 (`/api`)
- `POST /api/upload`: 批量上传文件
  - 支持最多10个文件
  - 并发控制（3个并发）
  - 自动重试机制（最多3次）
  - 本地文件备份

#### 历史记录 (`/api`)
- `GET /api/history/{business_id}`: 查询上传历史
  - 按业务单据ID查询
  - 返回统计信息和详细记录

#### 管理功能 (`/api/admin`)
- `GET /api/admin/records`: 分页查询记录
  - 支持搜索、筛选、日期范围
  - 分页参数（page, page_size）

- `GET /api/admin/export`: 导出数据
  - 导出为ZIP包（Excel + 图片）
  - 支持同样的筛选条件

- `GET /api/admin/statistics`: 获取统计数据
  - 总上传数、成功/失败数
  - 按单据类型统计

- `DELETE /api/admin/records`: 批量删除记录
  - 软删除策略
  - 不删除本地文件

#### 其他端点
- `GET /`: 上传页面入口
  - 参数: business_id, doc_number, doc_type

- `GET /admin`: 管理页面入口

- `GET /api/health`: 健康检查
  - 用于Docker健康检查

### 4.2 API文档
- Swagger UI: `http://localhost:10000/docs`
- ReDoc: `http://localhost:10000/redoc`

---

## 5. 数据模型

### 5.1 数据库Schema

**表名**: `upload_history`

| 字段名 | 类型 | 说明 | 索引 |
|--------|------|------|------|
| id | INTEGER | 主键，自增 | PRIMARY KEY |
| business_id | VARCHAR(50) | 业务单据ID（用友云） | INDEX |
| doc_number | VARCHAR(100) | 单据编号（业务标识） | INDEX |
| doc_type | VARCHAR(20) | 单据类型（销售/转库/其他） | INDEX |
| file_name | VARCHAR(255) | 文件名 | - |
| file_size | INTEGER | 文件大小（字节） | - |
| file_extension | VARCHAR(20) | 文件扩展名 | - |
| upload_time | DATETIME | 上传时间（北京时间） | INDEX |
| status | VARCHAR(20) | 状态（success/failed/pending） | INDEX |
| error_code | VARCHAR(50) | 错误码 | - |
| error_message | TEXT | 错误信息 | - |
| yonyou_file_id | VARCHAR(255) | 用友云文件ID | - |
| retry_count | INTEGER | 重试次数 | - |
| local_file_path | VARCHAR(500) | 本地文件路径 | - |
| deleted_at | TEXT | 软删除时间戳 | INDEX |
| created_at | DATETIME | 创建时间 | - |
| updated_at | DATETIME | 更新时间 | - |

**复合索引**:
- `(doc_type, upload_time)`: 用于按类型和时间查询

### 5.2 数据模型类

**UploadHistory** (`app/models/upload_history.py`):
- 简单的Python类，非ORM模型
- 用于在业务逻辑层传递数据
- 默认值处理和类型约束

---

## 6. 核心功能实现

### 6.1 用友云API集成

**认证流程**:
1. 使用AppKey和AppSecret生成HMAC-SHA256签名
2. 调用认证API获取access_token
3. Token缓存1小时（提前60秒刷新）
4. Token失效时自动刷新并重试

**上传流程**:
1. 读取文件内容
2. 获取并编码access_token
3. 构建multipart/form-data请求
4. 上传到用友云
5. 失败时自动重试（最多3次）
6. 保存上传历史到数据库
7. 本地备份文件

### 6.2 并发控制

**策略**: 使用`asyncio.Semaphore`限制并发数
- 最大并发上传数: 3
- 避免服务器压力过大
- 提供实时进度反馈

### 6.3 文件命名策略

**生成规则**:
- 基础名称: `{doc_number}{file_extension}`
- 冲突处理: 添加流水号 `{doc_number}-{counter}{file_extension}`
- 示例:
  - `SO20250103001.jpg`
  - `SO20250103001-1.jpg`
  - `SO20250103001-2.jpg`

### 6.4 时区处理

**统一策略**:
- 所有时间使用北京时间（UTC+8）
- 数据库存储naive datetime（无时区信息）
- 避免时区转换问题
- 工具函数:
  - `get_beijing_now()`: 带时区的datetime
  - `get_beijing_now_naive()`: 无时区的datetime
  - `format_beijing_time()`: 格式化为ISO字符串

### 6.5 软删除机制

**实现方式**:
- 添加`deleted_at`字段
- 删除时设置当前时间戳
- 查询时过滤`deleted_at IS NULL`
- 不删除本地文件
- 不调用用友云API

---

## 7. 配置管理

### 7.1 环境变量

**必需配置**:
- `YONYOU_APP_KEY`: 用友云AppKey（启动时验证）
- `YONYOU_APP_SECRET`: 用友云AppSecret（启动时验证）

**应用配置**:
- `APP_NAME`: 应用名称（默认: 单据上传管理系统）
- `APP_VERSION`: 版本号（默认: 1.0.0）
- `HOST`: 监听地址（默认: 0.0.0.0）
- `PORT`: 监听端口（默认: 10000）
- `DEBUG`: 调试模式（默认: false）

**用友云配置**:
- `YONYOU_BUSINESS_TYPE`: 业务类型（默认: yonbip-scm-scmsa）
- `YONYOU_AUTH_URL`: 认证URL
- `YONYOU_UPLOAD_URL`: 上传URL

**上传限制**:
- `MAX_FILE_SIZE`: 单文件最大大小（默认: 10MB）
- `MAX_FILES_PER_REQUEST`: 单次最多文件数（默认: 10）
- `ALLOWED_EXTENSIONS`: 允许的扩展名（.jpg, .jpeg, .png, .gif）

**重试配置**:
- `MAX_RETRY_COUNT`: 最大重试次数（默认: 3）
- `RETRY_DELAY`: 重试延迟（默认: 2秒）
- `REQUEST_TIMEOUT`: 请求超时（默认: 30秒）

**其他配置**:
- `MAX_CONCURRENT_UPLOADS`: 最大并发数（默认: 3）
- `DATABASE_URL`: 数据库URL（默认: sqlite:///data/uploads.db）
- `LOCAL_STORAGE_PATH`: 本地存储路径（默认: data/uploaded_files）
- `TOKEN_CACHE_DURATION`: Token缓存时长（默认: 3600秒）

### 7.2 配置加载顺序
1. 默认值（硬编码在`config.py`）
2. `.env`文件
3. 环境变量（覆盖前两者）

---

## 8. 测试策略

### 8.1 测试框架配置

**pytest.ini 配置**:
- 测试文件: `test_*.py`
- 测试目录: `tests/`
- 代码覆盖率要求: ≥70%
- 异步测试自动模式
- HTML覆盖率报告生成

**测试标记**:
- `@pytest.mark.slow`: 慢速测试
- `@pytest.mark.integration`: 集成测试
- `@pytest.mark.unit`: 单元测试
- `@pytest.mark.critical`: 关键测试

### 8.2 测试文件

主要测试文件:
- `test_database.py`: 数据库操作测试
- `test_yonyou_client.py`: 用友云客户端测试
- `test_upload_api.py`: 上传API测试
- `test_history_api.py`: 历史记录API测试
- `test_admin_delete.py`: 管理删除功能测试
- `test_integration.py`: 集成测试
- `conftest.py`: 测试配置和fixtures

### 8.3 测试覆盖率

- 应用代码: ~1,156行
- 测试代码: ~2,915行
- 测试代码与应用代码比例: ~2.5:1
- 测试覆盖率要求: 70%+

---

## 9. 部署架构

### 9.1 本地开发部署

**启动方式**:
```bash
# 使用run.py
python run.py

# 或直接使用uvicorn
uvicorn app.main:app --host 0.0.0.0 --port 10000
```

**开发特性**:
- 热重载（DEBUG=true）
- 实时日志输出
- 虚拟环境支持

### 9.2 Docker部署

**镜像特性**:
- 基础镜像: Python 3.9-slim
- 优化层缓存
- 健康检查支持
- 数据卷持久化

**Docker Compose配置**:
- 端口映射: 10000:10000
- 数据卷: `./data:/app/data`, `./logs:/app/logs`
- 自动重启策略: unless-stopped
- 健康检查: 30秒间隔
- 网络: bridge模式

**部署命令**:
```bash
# 构建并启动
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

### 9.3 生产环境建议

根据`DOCKER_DEPLOYMENT.md`文档:
- 使用Nginx反向代理
- 配置HTTPS
- 限制资源使用
- 使用外部卷存储
- 配置日志轮转
- 设置正确的时区（Asia/Shanghai）

---

## 10. 开发约定

### 10.1 编码标准

**Python代码规范**:
- 使用类型提示（Type Hints）
- 异步函数使用`async/await`
- 文档字符串（Docstrings）用于API函数
- 错误处理使用HTTPException

**命名约定**:
- 文件名: 小写+下划线（snake_case）
- 类名: 大驼峰（PascalCase）
- 函数名: 小写+下划线（snake_case）
- 常量: 大写+下划线（UPPER_SNAKE_CASE）

### 10.2 API设计约定

**RESTful规范**:
- GET: 查询资源
- POST: 创建/上传资源
- DELETE: 删除资源
- PUT/PATCH: 更新资源（未使用）

**响应格式**:
```json
{
  "success": true/false,
  "data": {...},
  "message": "提示信息",
  "error_code": "错误码"
}
```

**错误处理**:
- HTTP 400: 客户端错误（参数错误）
- HTTP 404: 资源不存在
- HTTP 500: 服务器错误

### 10.3 数据库约定

**索引策略**:
- 为常用查询字段创建索引
- business_id, doc_number, doc_type, upload_time
- 复合索引: (doc_type, upload_time)

**时间字段**:
- 统一使用北京时间（UTC+8）
- 存储为naive datetime（ISO格式字符串）
- 字段名: upload_time, created_at, updated_at, deleted_at

### 10.4 Git工作流

**分支策略**:
- main: 主分支（当前状态干净）
- 功能开发直接提交到main

**提交信息规范**:
从Git历史看出的约定:
- 简短描述（中文）
- 示例: "jsqr本地化", "docker部署", "修复时区bug"

---

## 11. 集成点分析

### 11.1 新功能集成点

如需添加新功能，建议的集成位置:

**API功能扩展**:
- 位置: `app/api/` 目录
- 创建新的路由模块
- 在 `app/main.py` 中注册路由

**业务逻辑扩展**:
- 位置: `app/core/` 目录
- 创建新的客户端或服务类
- 遵循现有的设计模式

**数据模型扩展**:
- 位置: `app/models/` 目录
- 数据库schema修改在 `app/core/database.py`
- 使用ALTER TABLE添加字段（兼容性）

**前端页面扩展**:
- 位置: `app/static/` 目录
- HTML页面、CSS样式、JS脚本
- 注意移动端适配

### 11.2 外部系统集成

**当前集成**:
- 用友云API（认证 + 文件上传）
- 客户端: `YonYouClient`

**扩展建议**:
- 参考 `yonyou_client.py` 的设计模式
- 实现独立的客户端类
- 支持Token缓存和重试机制
- 添加相应的测试用例

---

## 12. 约束和注意事项

### 12.1 技术约束

**文件上传限制**:
- 单文件最大: 10MB
- 单次最多: 10个文件
- 允许格式: jpg, jpeg, png, gif

**并发限制**:
- 同时上传: 3个文件
- 避免服务器压力过大

**数据库约束**:
- 使用SQLite（单文件数据库）
- 不支持真正的并发写入
- 适合轻量级场景

**网络依赖**:
- 依赖用友云API可用性
- Token有效期1小时
- 需要稳定的网络连接

### 12.2 安全注意事项

**敏感信息**:
- AppKey和AppSecret必须通过环境变量配置
- 不要提交 `.env` 文件到Git
- Docker部署时使用环境变量注入

**API安全**:
- 当前无认证机制（内部工具）
- 建议添加访问控制（如IP白名单）
- CORS配置为允许所有来源（需要限制）

**文件安全**:
- 文件类型验证（仅允许图片）
- 文件大小限制
- 文件名规范化（避免路径遍历）

### 12.3 性能注意事项

**Token缓存**:
- 缓存时长: 1小时
- 提前60秒刷新
- 减少API调用

**并发控制**:
- 限制为3个并发上传
- 使用Semaphore控制
- 避免过载

**数据库索引**:
- 已为常用查询创建索引
- 注意索引维护成本

**文件存储**:
- 本地文件备份可能占用大量磁盘空间
- 需要定期清理策略

### 12.4 兼容性注意事项

**Python版本**:
- 要求: Python 3.8+
- 使用Python 3.9特性（如类型提示改进）

**数据库迁移**:
- 使用ALTER TABLE添加字段
- 检查字段是否存在（兼容旧版本）
- 不使用ORM，需要手动管理schema

**浏览器兼容性**:
- 移动端优先设计
- 使用现代浏览器API（如File API）
- jsQR库依赖Canvas API

---

## 13. 文档资源

### 13.1 项目文档

**主要文档**:
- `README.md`: 项目介绍、安装、使用指南
- `DOCKER_DEPLOYMENT.md`: Docker部署详细指南
- `.env.example`: 环境变量配置示例

**API文档**:
- Swagger UI: `/docs`
- ReDoc: `/redoc`
- 自动生成（FastAPI特性）

### 13.2 代码注释

**注释风格**:
- API函数有详细的Docstrings
- 参数说明和返回值说明
- 业务逻辑有中文注释

**示例**:
```python
async def upload_files(
    business_id: str = Form(..., description="业务单据ID"),
    doc_number: str = Form(..., description="单据编号"),
    doc_type: str = Form(..., description="单据类型"),
    files: List[UploadFile] = File(...)
):
    """
    批量上传文件到用友云

    请求参数:
    - business_id: 业务单据ID（纯数字，用于用友云API）
    - doc_number: 单据编号（业务标识，如SO20250103001）
    - doc_type: 单据类型（销售/转库/其他）
    - files: 文件列表 (最多10个)
    """
```

---

## 14. 建议的开发流程

### 14.1 添加新功能

**步骤**:
1. 在相应的模块中添加代码（api/, core/, models/）
2. 更新数据库schema（如需要）
3. 编写单元测试
4. 更新API文档（Docstrings）
5. 本地测试验证
6. 提交代码

### 14.2 修改现有功能

**步骤**:
1. 查看相关测试用例
2. 理解现有逻辑
3. 进行修改
4. 更新测试用例
5. 运行测试确保覆盖率
6. 提交代码

### 14.3 测试流程

**本地测试**:
```bash
# 运行所有测试
pytest

# 运行特定测试
pytest tests/test_upload_api.py

# 查看覆盖率
pytest --cov=app --cov-report=html
```

**手动测试**:
1. 启动服务: `python run.py`
2. 访问页面: `http://localhost:10000/`
3. 测试上传功能
4. 检查数据库: `sqlite3 data/uploads.db`

---

## 15. 性能特性

### 15.1 异步处理

**FastAPI + httpx**:
- 全异步架构
- 支持高并发请求
- 非阻塞IO操作

**并发上传**:
- asyncio.gather并发执行
- Semaphore控制并发数
- 实时进度反馈

### 15.2 缓存机制

**Token缓存**:
- 内存缓存（字典）
- 有效期1小时
- 自动刷新

### 15.3 数据库优化

**索引策略**:
- business_id: 快速查询特定单据
- doc_number: 按单据编号查询
- doc_type: 按类型筛选
- upload_time: 时间范围查询
- (doc_type, upload_time): 复合查询

---

## 16. 监控和日志

### 16.1 日志输出

**日志配置**:
- 输出到控制台
- log_level: INFO
- 可重定向到文件

**Docker日志**:
- docker-compose logs
- 持久化到 `./logs` 目录

### 16.2 健康检查

**端点**: `/api/health`
- 返回状态和版本信息
- Docker健康检查使用
- 30秒检查间隔

### 16.3 错误跟踪

**数据库记录**:
- 上传失败记录
- 错误码和错误信息
- 重试次数

**日志输出**:
- 异常信息打印到控制台
- 关键操作日志

---

## 17. 未来扩展方向

基于当前架构，可能的扩展方向:

### 17.1 功能扩展
- [ ] 用户认证和权限管理
- [ ] 更多单据类型支持
- [ ] 图片预处理（压缩、裁剪）
- [ ] OCR识别功能
- [ ] 批量下载功能
- [ ] 更详细的统计报表

### 17.2 性能优化
- [ ] 使用Redis缓存Token
- [ ] 异步任务队列（Celery）
- [ ] CDN加速静态资源
- [ ] 数据库连接池
- [ ] 文件上传进度显示

### 17.3 架构优化
- [ ] 迁移到PostgreSQL/MySQL
- [ ] 使用ORM（SQLAlchemy）
- [ ] 微服务拆分
- [ ] 消息队列集成
- [ ] 分布式文件存储

---

## 18. 总结

### 18.1 项目优势

✅ **轻量级**: 无重型依赖，启动快速
✅ **异步架构**: 支持高并发
✅ **完整测试**: 70%+代码覆盖率
✅ **Docker支持**: 容器化部署
✅ **移动端友好**: 响应式设计
✅ **本地备份**: 数据安全性高
✅ **软删除**: 数据可恢复

### 18.2 技术亮点

- **FastAPI**: 现代化Web框架
- **异步处理**: asyncio + httpx
- **Token管理**: 自动缓存和刷新
- **并发控制**: Semaphore限制
- **时区处理**: 统一北京时间
- **测试完善**: 单元测试+集成测试
- **文档齐全**: API文档+部署文档

### 18.3 适用场景

✅ 企业内部工具
✅ 移动端上传需求
✅ 轻量级文件管理
✅ 快速原型开发

### 18.4 不适用场景

❌ 大规模并发（SQLite限制）
❌ 复杂权限管理
❌ 海量文件存储
❌ 多租户SaaS应用

---

**报告生成说明**:
- 本报告基于代码静态分析生成
- 涵盖项目结构、技术栈、架构设计、开发约定等方面
- 为新功能开发提供完整的上下文信息
- 建议结合实际代码阅读以深入理解

**文档维护**:
- 随着项目演进，需要定期更新本文档
- 新增功能时补充相应章节
- 架构变更时及时同步

---

*生成时间: 2025-10-17*
*文档版本: 1.0.0*
