# 仓库上下文分析报告

## 项目概览

### 项目类型和目的
**项目名称**: 单据上传管理系统 (Document Upload Management System)

**项目类型**: Web应用 - 企业级文件上传系统

**核心目的**:
- 提供移动端友好的图片上传界面，通过扫描二维码快速访问
- 将图片文件上传至用友云存储API
- 管理和查询上传历史记录
- 支持多种业务类型（销售、转库等）的单据图片管理

### 业务场景
系统主要用于以下场景：
1. **移动端快速上传**: 用户通过扫描二维码访问上传页面，拍照或选择图片上传
2. **批量处理**: 单次最多支持10张图片批量上传
3. **业务关联**: 图片与具体业务单据ID关联（如销售订单、转库单）
4. **历史追溯**: 查询特定业务单据的所有上传记录
5. **管理后台**: 提供管理界面查看、筛选、导出、删除上传记录

---

## 技术栈详情

### 编程语言
- **Python 3.9+**: 主要开发语言

### 后端框架与核心库

#### Web框架
- **FastAPI 0.104.1**: 现代化、高性能的异步Web框架
  - 自动生成API文档（Swagger UI、ReDoc）
  - 基于Pydantic的数据验证
  - 原生支持异步操作

#### HTTP客户端
- **httpx 0.25.1**: 异步HTTP客户端
  - 用于调用用友云API
  - 支持超时控制和重试机制

#### 数据验证与配置
- **Pydantic 2.5.0**: 数据验证和设置管理
- **pydantic-settings 2.1.0**: 环境变量配置管理
- **python-dotenv 1.0.0**: .env文件解析

#### 文件处理
- **python-multipart 0.0.6**: multipart/form-data解析
- **Pillow 10.1.0**: 图像处理（用于测试）
- **openpyxl 3.1.2**: Excel文件生成（导出功能）

#### 数据库
- **SQLite**: 轻量级嵌入式数据库
  - 无需额外服务器
  - 存储上传历史记录
  - 支持索引优化查询

#### Web服务器
- **uvicorn[standard] 0.24.0**: ASGI服务器
  - 支持热重载（开发模式）
  - 高性能异步IO

#### 测试框架
- **pytest 7.4.3**: 测试框架
- **pytest-asyncio 0.21.1**: 异步测试支持
- **pytest-cov 4.1.0**: 代码覆盖率
- **pytest-mock 3.12.0**: Mock支持

### 前端技术栈
- **原生HTML/CSS/JavaScript**: 无前端框架依赖
- **响应式设计**: 移动端优先
- **jsQR**: 本地化二维码扫描库（130KB）
- **异步上传**: 使用Fetch API

### 部署与容器化
- **Docker**: 容器化部署
- **Docker Compose**: 多容器编排
- **Python 3.9-slim基础镜像**: 优化镜像体积

---

## 项目结构分析

### 目录结构
```
单据上传管理/
├── app/                        # 应用主目录
│   ├── __init__.py
│   ├── main.py                 # FastAPI应用入口
│   ├── api/                    # API路由模块
│   │   ├── __init__.py
│   │   ├── upload.py           # 文件上传API
│   │   ├── history.py          # 历史记录API
│   │   └── admin.py            # 管理后台API
│   ├── core/                   # 核心模块
│   │   ├── __init__.py
│   │   ├── config.py           # 配置管理（Pydantic Settings）
│   │   ├── database.py         # 数据库操作
│   │   ├── yonyou_client.py    # 用友云API客户端
│   │   └── timezone.py         # 北京时区工具
│   ├── models/                 # 数据模型
│   │   ├── __init__.py
│   │   └── upload_history.py   # 上传历史模型
│   └── static/                 # 静态资源
│       ├── index.html          # 上传页面
│       ├── admin.html          # 管理页面
│       ├── css/                # 样式文件
│       │   ├── style.css       # 上传页样式
│       │   └── admin.css       # 管理页样式
│       └── js/                 # 前端脚本
│           ├── app.js          # 上传页逻辑
│           ├── admin.js        # 管理页逻辑
│           └── jsQR.min.js     # 二维码扫描库
├── tests/                      # 测试目录
│   ├── conftest.py             # 测试配置和fixtures
│   ├── test_upload_api.py      # 上传API测试
│   ├── test_history_api.py     # 历史API测试
│   ├── test_database.py        # 数据库测试
│   ├── test_yonyou_client.py   # 用友云客户端测试
│   ├── test_integration.py     # 集成测试
│   └── ...                     # 其他测试文件
├── data/                       # 数据目录（.gitignore）
│   ├── uploads.db              # SQLite数据库
│   └── uploaded_files/         # 本地文件存储
├── logs/                       # 日志目录（.gitignore）
├── .env                        # 环境变量配置
├── .gitignore                  # Git忽略文件
├── requirements.txt            # Python依赖
├── run.py                      # 启动脚本
├── Dockerfile                  # Docker镜像定义
├── docker-compose.yml          # Docker编排配置
├── README.md                   # 项目文档
└── DOCKER_DEPLOYMENT.md        # Docker部署指南
```

### 模块组织方式

#### 1. **API层**（app/api/）
- **职责分离**: 按功能划分为独立的路由模块
- **upload.py**: 文件上传核心逻辑
  - 批量上传处理
  - 文件验证（大小、类型、数量）
  - 并发控制（Semaphore限制3个并发）
  - 重试机制（最多3次）
  - 数据库记录保存
- **history.py**: 历史记录查询
  - 按业务单据ID查询
  - 统计成功/失败数量
- **admin.py**: 管理后台功能
  - 分页查询记录
  - 多条件筛选（单据类型、产品类型、日期范围）
  - 导出ZIP包（Excel + 图片）
  - 软删除记录

#### 2. **核心层**（app/core/）
- **config.py**: 配置管理
  - 使用Pydantic Settings从环境变量加载配置
  - 配置验证（必需参数检查）
  - 单例模式（@lru_cache）
- **database.py**: 数据库操作
  - 数据库初始化（建表、索引）
  - 连接管理
  - 动态字段添加（兼容旧数据库）
- **yonyou_client.py**: 用友云API客户端
  - Token管理（HMAC-SHA256签名）
  - Token缓存（1小时过期）
  - 文件上传（multipart/form-data）
  - 自动重试（Token过期时刷新）
- **timezone.py**: 时区工具
  - 统一使用北京时间（UTC+8）
  - 提供带时区和不带时区的时间生成函数

#### 3. **数据模型层**（app/models/）
- **upload_history.py**: 上传历史记录模型
  - 简单的Python类（非ORM）
  - 与数据库表结构对应

#### 4. **静态资源层**（app/static/）
- **前后端分离**: 静态HTML/CSS/JS文件
- **移动端优先**: 响应式设计
- **本地化依赖**: jsQR库本地存储（避免CDN依赖）

---

## 代码组织模式

### 设计模式

#### 1. **单例模式**
- **配置管理**: `get_settings()`使用`@lru_cache()`实现单例
- **全局YonYouClient实例**: 在upload.py中共享

#### 2. **工厂模式**
- **数据库连接**: `get_db_connection()`每次创建新连接

#### 3. **策略模式**
- **业务类型映射**: `DOC_TYPE_TO_BUSINESS_TYPE`字典映射不同业务类型到用友云API参数

#### 4. **责任链模式**
- **文件验证**: 多层验证（类型 -> 大小 -> 数量）

### 异步编程模式

#### 1. **异步IO**
- **FastAPI路由**: 使用`async def`定义
- **HTTP请求**: 使用`httpx.AsyncClient`异步调用用友云API
- **并发控制**: `asyncio.Semaphore(3)`限制并发数

#### 2. **并发上传**
```python
# app/api/upload.py
semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_UPLOADS)

async def upload_single_file(upload_file: UploadFile):
    async with semaphore:
        # 上传逻辑
        ...

# 并发执行
results = await asyncio.gather(*[upload_single_file(f) for f in files])
```

#### 3. **重试机制**
```python
# app/api/upload.py
for attempt in range(settings.MAX_RETRY_COUNT):
    result = await yonyou_client.upload_file(...)
    if result["success"]:
        break
    else:
        if attempt < settings.MAX_RETRY_COUNT - 1:
            await asyncio.sleep(settings.RETRY_DELAY)
```

### 错误处理模式

#### 1. **统一错误响应**
```python
return {
    "success": False,
    "error_code": "FILE_TOO_LARGE",
    "error_message": "文件大小超过10MB限制"
}
```

#### 2. **HTTPException**
```python
if not business_id or not business_id.isdigit():
    raise HTTPException(status_code=400, detail="business_id必须为纯数字")
```

#### 3. **Try-Except包裹**
```python
try:
    # 操作
except Exception as e:
    return {
        "success": False,
        "error_code": "NETWORK_ERROR",
        "error_message": str(e)
    }
```

---

## 用友云集成详情

### API认证机制

#### 1. **签名算法**（HMAC-SHA256）
```python
# app/core/yonyou_client.py
def _generate_signature(self, timestamp: str) -> str:
    # 构建待签名字符串
    string_to_sign = f"appKey{self.app_key}timestamp{timestamp}"

    # HMAC-SHA256签名
    hmac_code = hmac.new(
        self.app_secret.encode(),
        string_to_sign.encode(),
        hashlib.sha256
    ).digest()

    # Base64编码 + URL编码
    signature = urllib.parse.quote(base64.b64encode(hmac_code).decode())
    return signature
```

#### 2. **Token获取与缓存**
```python
async def get_access_token(self, force_refresh: bool = False) -> str:
    # 检查缓存
    if not force_refresh and self._token_cache:
        if get_beijing_now() < self._token_cache["expires_at"]:
            return self._token_cache["access_token"]

    # 获取新Token
    timestamp = str(int(time.time() * 1000))
    signature = self._generate_signature(timestamp)
    url = f"{self.auth_url}?appKey={self.app_key}&timestamp={timestamp}&signature={signature}"

    # 发送请求
    async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT) as client:
        response = await client.get(url)
        result = response.json()

    # 缓存Token（提前60秒过期）
    if result.get("code") == "00000":
        access_token = result["data"]["access_token"]
        expires_in = result["data"].get("expires_in", 3600)
        self._token_cache = {
            "access_token": access_token,
            "expires_at": get_beijing_now() + timedelta(seconds=expires_in - 60)
        }
        return access_token
```

#### 3. **Token自动刷新**
```python
# Token无效时自动刷新重试
error_code = str(result.get("code"))
if error_code in ["1090003500065", "310036"] and retry_count == 0:
    access_token = await self.get_access_token(force_refresh=True)
    return await self.upload_file(file_content, file_name, business_id, retry_count + 1, business_type)
```

### 文件上传流程

#### 1. **API端点**
```
POST https://c4.yonyoucloud.com/iuap-api-gateway/yonbip/uspace/iuap-apcom-file/rest/v1/file
参数:
  - access_token: JWT令牌（URL编码）
  - businessType: 业务类型（yonbip-scm-scmsa/yonbip-scm-stock）
  - businessId: 业务单据ID（纯数字）
Body:
  - files: multipart/form-data格式文件
```

#### 2. **业务类型映射**
```python
# app/api/upload.py
DOC_TYPE_TO_BUSINESS_TYPE = {
    "销售": "yonbip-scm-scmsa",
    "转库": "yonbip-scm-stock",
    "其他": "yonbip-scm-stock"
}
```

#### 3. **上传请求构建**
```python
async def upload_file(self, file_content: bytes, file_name: str,
                     business_id: str, business_type: Optional[str] = None):
    access_token = await self.get_access_token()
    encoded_token = urllib.parse.quote(access_token, safe='')
    effective_business_type = business_type or self.business_type

    url = f"{self.upload_url}?access_token={encoded_token}&businessType={effective_business_type}&businessId={business_id}"

    files = {
        "files": (file_name, file_content, "application/octet-stream")
    }

    async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT) as client:
        response = await client.post(url, files=files)
        result = response.json()
```

### 错误处理与重试

#### 1. **Token错误**
- **错误码**: 1090003500065（token过期）、310036（非法token）
- **处理**: 自动刷新Token并重试（仅重试1次）

#### 2. **网络错误**
- **错误码**: NETWORK_ERROR
- **处理**: 记录错误信息，不重试（由上层重试机制处理）

#### 3. **业务错误**
- **错误码**: 用友云返回的业务错误码
- **处理**: 记录错误信息，不重试

---

## 图片上传流程详解

### 前端上传流程（app/static/js/app.js）

#### 1. **文件选择**
- 移动端支持拍照和相册选择
- 支持拖拽上传（桌面端）
- 最多选择10张图片

#### 2. **前端验证**
```javascript
// 文件类型验证
const allowedTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif'];
if (!allowedTypes.includes(file.type)) {
    return; // 忽略不支持的文件
}

// 文件大小验证（10MB）
const maxSize = 10 * 1024 * 1024;
if (file.size > maxSize) {
    alert('文件过大');
    return;
}
```

#### 3. **并发上传控制**
```javascript
// 限制同时上传3个文件
const MAX_CONCURRENT = 3;
let activeUploads = 0;
const queue = [...files];

async function processQueue() {
    while (queue.length > 0 && activeUploads < MAX_CONCURRENT) {
        activeUploads++;
        const file = queue.shift();
        await uploadFile(file);
        activeUploads--;
    }
}
```

#### 4. **进度显示**
- 每个文件独立显示进度
- 实时更新上传状态（上传中、成功、失败）

### 后端处理流程（app/api/upload.py）

#### 1. **请求验证**
```python
# 参数验证
if not business_id or not business_id.isdigit():
    raise HTTPException(status_code=400, detail="business_id必须为纯数字")

if doc_type not in ["销售", "转库", "其他"]:
    raise HTTPException(status_code=400, detail="doc_type必须为: 销售/转库/其他")

# 文件数量验证
if len(files) > settings.MAX_FILES_PER_REQUEST:
    raise HTTPException(status_code=400, detail="单次最多上传10个文件")

# 文件类型验证
for file in files:
    file_ext = "." + file.filename.split(".")[-1].lower()
    if file_ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="不支持的文件格式")
```

#### 2. **并发上传**
```python
# 并发控制（Semaphore限制3个并发）
semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_UPLOADS)

async def upload_single_file(upload_file: UploadFile):
    async with semaphore:
        # 读取文件
        file_content = await upload_file.read()
        file_size = len(file_content)

        # 验证文件大小
        if file_size > settings.MAX_FILE_SIZE:
            return {"success": False, "error_code": "FILE_TOO_LARGE", ...}

        # 生成唯一文件名（并发安全）
        file_extension = "." + upload_file.filename.split(".")[-1].lower()
        new_filename, local_file_path = generate_unique_filename(
            doc_number, file_extension, storage_path
        )

        # 创建历史记录
        history = UploadHistory(
            business_id=business_id,
            doc_number=doc_number,
            doc_type=doc_type,
            product_type=product_type,
            file_name=new_filename,
            ...
        )

        # 重试上传（最多3次）
        for attempt in range(settings.MAX_RETRY_COUNT):
            result = await yonyou_client.upload_file(...)
            if result["success"]:
                # 保存文件到本地
                save_file_locally(file_content, local_file_path)
                # 保存到数据库
                save_upload_history(history)
                return {"success": True, ...}
            else:
                if attempt < settings.MAX_RETRY_COUNT - 1:
                    await asyncio.sleep(settings.RETRY_DELAY)

# 并发执行
results = await asyncio.gather(*[upload_single_file(f) for f in files])
```

#### 3. **文件命名策略**（并发安全）
```python
def generate_unique_filename(doc_number: str, file_extension: str, storage_path: str):
    """
    生成唯一文件名（并发安全）
    格式: {doc_number}_{timestamp}_{uuid_short}{extension}
    示例: SO20250103001_20251020143025_a3f2b1c4.jpg
    """
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    short_uuid = str(uuid.uuid4()).replace('-', '')[:8]
    new_filename = f"{doc_number}_{timestamp}_{short_uuid}{file_extension}"
    full_path = os.path.join(storage_path, new_filename)
    return new_filename, full_path
```

#### 4. **本地文件存储**
```python
def save_file_locally(file_content: bytes, file_path: str):
    # 确保目录存在
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    # 保存文件
    with open(file_path, 'wb') as f:
        f.write(file_content)
```

#### 5. **数据库记录**
```python
def save_upload_history(history: UploadHistory):
    conn = get_db_connection()
    cursor = conn.cursor()

    beijing_now = get_beijing_now_naive()
    upload_time_str = beijing_now.isoformat()

    cursor.execute("""
        INSERT INTO upload_history
        (business_id, doc_number, doc_type, product_type, file_name, file_size,
         file_extension, upload_time, status, error_code, error_message,
         yonyou_file_id, retry_count, local_file_path, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (...))

    conn.commit()
    conn.close()
```

### 重试机制

#### 1. **前端重试**（用户手动）
- 失败文件显示重试按钮
- 用户点击重新上传

#### 2. **后端自动重试**（最多3次）
```python
# app/api/upload.py
for attempt in range(settings.MAX_RETRY_COUNT):  # MAX_RETRY_COUNT = 3
    result = await yonyou_client.upload_file(...)
    if result["success"]:
        history.retry_count = attempt
        break
    else:
        if attempt < settings.MAX_RETRY_COUNT - 1:
            await asyncio.sleep(settings.RETRY_DELAY)  # RETRY_DELAY = 2秒
        else:
            history.status = "failed"
            history.error_code = result["error_code"]
            history.retry_count = attempt
```

#### 3. **Token刷新重试**
```python
# app/core/yonyou_client.py
if error_code in ["1090003500065", "310036"] and retry_count == 0:
    access_token = await self.get_access_token(force_refresh=True)
    return await self.upload_file(file_content, file_name, business_id, retry_count + 1)
```

---

## 数据库设计

### 表结构：upload_history

```sql
CREATE TABLE IF NOT EXISTS upload_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_id VARCHAR(50) NOT NULL,      -- 业务单据ID（用友云）
    doc_number VARCHAR(100),               -- 单据编号（业务标识）
    doc_type VARCHAR(20),                  -- 单据类型（销售/转库/其他）
    product_type TEXT DEFAULT NULL,        -- 产品类型（油脂/快消等）
    file_name VARCHAR(255) NOT NULL,       -- 文件名
    file_size INTEGER NOT NULL,            -- 文件大小（字节）
    file_extension VARCHAR(20),            -- 文件扩展名
    upload_time DATETIME,                  -- 上传时间（北京时间）
    status VARCHAR(20) NOT NULL,           -- 状态（pending/success/failed）
    error_code VARCHAR(50),                -- 错误码
    error_message TEXT,                    -- 错误信息
    yonyou_file_id VARCHAR(255),           -- 用友云文件ID
    retry_count INTEGER DEFAULT 0,         -- 重试次数
    local_file_path VARCHAR(500),          -- 本地文件路径
    deleted_at TEXT DEFAULT NULL,          -- 软删除时间
    created_at DATETIME,                   -- 创建时间
    updated_at DATETIME                    -- 更新时间
)
```

### 索引

```sql
-- 业务单据ID索引（高频查询）
CREATE INDEX idx_business_id ON upload_history(business_id);

-- 上传时间索引（排序、时间范围查询）
CREATE INDEX idx_upload_time ON upload_history(upload_time);

-- 状态索引（筛选成功/失败记录）
CREATE INDEX idx_status ON upload_history(status);

-- 单据编号索引（管理页面搜索）
CREATE INDEX idx_doc_number ON upload_history(doc_number);

-- 单据类型索引（管理页面筛选）
CREATE INDEX idx_doc_type ON upload_history(doc_type);

-- 复合索引（单据类型 + 上传时间）
CREATE INDEX idx_doc_type_upload_time ON upload_history(doc_type, upload_time);

-- 软删除索引（筛选未删除记录）
CREATE INDEX idx_deleted_at ON upload_history(deleted_at);

-- 产品类型索引（产品维度筛选）
CREATE INDEX idx_product_type ON upload_history(product_type);
```

### 数据库特性

#### 1. **动态字段添加**（向后兼容）
```python
# app/core/database.py
def init_database():
    # 检查字段是否存在
    cursor.execute("PRAGMA table_info(upload_history)")
    columns = [column[1] for column in cursor.fetchall()]

    # 动态添加缺失字段
    if 'doc_number' not in columns:
        cursor.execute("ALTER TABLE upload_history ADD COLUMN doc_number VARCHAR(100)")

    if 'product_type' not in columns:
        cursor.execute("ALTER TABLE upload_history ADD COLUMN product_type TEXT DEFAULT NULL")
```

#### 2. **软删除**
- 不物理删除记录，仅标记`deleted_at`字段
- 查询时过滤：`WHERE deleted_at IS NULL`
- 支持数据恢复和审计

#### 3. **北京时区**
- 所有时间字段使用北京时间（UTC+8）
- 统一使用`get_beijing_now_naive()`生成时间

---

## 管理功能

### 管理页面（/admin）

#### 1. **记录列表**
- 分页显示（默认20条/页）
- 支持搜索（单据编号、文件名）
- 多条件筛选：
  - 单据类型（销售/转库/其他）
  - 产品类型（油脂/快消等）
  - 日期范围

#### 2. **导出功能**
```python
# app/api/admin.py
@router.get("/export")
async def export_records(...):
    # 查询匹配记录
    cursor.execute(f"SELECT ... FROM upload_history WHERE {where_sql} ...")

    # 创建ZIP包
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # 生成Excel表格
        wb = Workbook()
        ws = wb.active
        ws.append(["单据编号", "单据类型", "产品类型", "业务ID", "上传时间", "文件名", "文件大小"])
        for row in rows:
            ws.append([...])

        # 添加本地图片文件
        if local_file_path and os.path.exists(local_file_path):
            arcname = os.path.join("images", os.path.basename(local_file_path))
            zipf.write(local_file_path, arcname=arcname)

        # 添加Excel到ZIP
        zipf.write(excel_temp_path, arcname="upload_records.xlsx")

    return FileResponse(path=zip_path, media_type="application/zip", ...)
```

#### 3. **软删除**
```python
@router.delete("/records")
async def delete_records(request: DeleteRecordsRequest):
    current_time = get_beijing_now_naive().isoformat()
    cursor.execute(f"""
        UPDATE upload_history
        SET deleted_at = ?
        WHERE id IN ({placeholders})
        AND deleted_at IS NULL
    """, [current_time] + request.ids)
```

#### 4. **统计数据**
```python
@router.get("/statistics")
async def get_statistics():
    # 总上传数、成功数、失败数
    cursor.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success,
            SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed
        FROM upload_history
        WHERE deleted_at IS NULL
    """)

    # 按单据类型统计
    cursor.execute("""
        SELECT doc_type, COUNT(*) as count
        FROM upload_history
        WHERE doc_type IS NOT NULL AND deleted_at IS NULL
        GROUP BY doc_type
    """)
```

---

## 配置管理

### 环境变量（.env）

```env
# 应用配置
APP_NAME=单据上传管理系统
APP_VERSION=1.0.0
HOST=0.0.0.0
PORT=10000
DEBUG=false

# 用友云配置（必需）
YONYOU_APP_KEY=ab2bbb774d284bbca947e8c9938332bf
YONYOU_APP_SECRET=d6ef04c33f3f6eaca7076439f6dc955474f3aa8f
YONYOU_BUSINESS_TYPE=yonbip-scm-scmsa
YONYOU_AUTH_URL=https://c4.yonyoucloud.com/iuap-api-auth/open-auth/selfAppAuth/base/v1/getAccessToken
YONYOU_UPLOAD_URL=https://c4.yonyoucloud.com/iuap-api-gateway/yonbip/uspace/iuap-apcom-file/rest/v1/file

# 上传配置
MAX_FILE_SIZE=10485760              # 10MB
MAX_FILES_PER_REQUEST=10
ALLOWED_EXTENSIONS=.jpg,.jpeg,.png,.gif

# 重试配置
MAX_RETRY_COUNT=3
RETRY_DELAY=2
REQUEST_TIMEOUT=30

# 并发控制
MAX_CONCURRENT_UPLOADS=3

# 数据库配置
DATABASE_URL=sqlite:///data/uploads.db

# 本地文件存储
LOCAL_STORAGE_PATH=data/uploaded_files

# Token缓存配置
TOKEN_CACHE_DURATION=3600
```

### 配置验证（app/core/config.py）

```python
class Settings(BaseSettings):
    # 必需字段验证
    YONYOU_APP_KEY: Optional[str] = None
    YONYOU_APP_SECRET: Optional[str] = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.YONYOU_APP_KEY:
            raise ValueError("缺少必需的环境变量: YONYOU_APP_KEY")
        if not self.YONYOU_APP_SECRET:
            raise ValueError("缺少必需的环境变量: YONYOU_APP_SECRET")
```

---

## 测试策略

### 测试覆盖范围

#### 1. **单元测试**
- `test_upload_api.py`: 上传API测试（文件验证、重试机制、并发控制）
- `test_history_api.py`: 历史记录API测试
- `test_database.py`: 数据库操作测试
- `test_yonyou_client.py`: 用友云客户端测试（签名、Token、上传）

#### 2. **集成测试**
- `test_integration.py`: 端到端测试

#### 3. **并发测试**
- `test_concurrent_upload_fix.py`: 并发上传测试
- `test_concurrent_filename.py`: 并发文件命名冲突测试

#### 4. **产品类型测试**
- `test_product_type_*.py`: 产品类型字段相关测试

### 测试工具

#### 1. **Fixtures（conftest.py）**
```python
@pytest.fixture
def test_image_bytes():
    """生成测试图片数据"""
    img = Image.new('RGB', (100, 100), color='red')
    buffer = BytesIO()
    img.save(buffer, format='JPEG')
    return buffer.getvalue()

@pytest.fixture
def mock_upload_response_success():
    """Mock用友云上传成功响应"""
    return {
        "code": "200",
        "data": {
            "data": [{
                "id": "test_file_id_12345",
                "fileName": "test.jpg",
                "fileExtension": ".jpg",
                "fileSize": 1024
            }]
        }
    }
```

#### 2. **Mock策略**
```python
# Mock用友云API
with patch('app.api.upload.yonyou_client.upload_file', new_callable=AsyncMock) as mock_upload:
    mock_upload.return_value = {"success": True, ...}

# Mock数据库
with patch('app.api.upload.get_db_connection') as mock_db_conn:
    mock_conn = sqlite3.connect(test_db_path)
    mock_db_conn.return_value = mock_conn
```

### 测试命令

```bash
# 运行所有测试
pytest

# 运行指定测试文件
pytest tests/test_upload_api.py

# 运行指定测试类
pytest tests/test_upload_api.py::TestUploadAPI

# 运行指定测试方法
pytest tests/test_upload_api.py::TestUploadAPI::test_upload_single_file_success

# 查看代码覆盖率
pytest --cov=app --cov-report=html
```

---

## 部署方式

### 1. **本地开发部署**
```bash
# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
vi .env

# 启动服务
python run.py
```

### 2. **Docker部署**
```bash
# 构建镜像
docker build -t upload-manager .

# 运行容器
docker run -d \
  -p 10000:10000 \
  -v ./data:/app/data \
  -v ./logs:/app/logs \
  --env-file .env \
  upload-manager
```

### 3. **Docker Compose部署**
```bash
# 启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

### 4. **健康检查**
```bash
# HTTP端点
curl http://localhost:10000/api/health

# Docker健康检查
docker inspect --format='{{json .State.Health}}' upload-manager
```

---

## 开发约定与编码标准

### 1. **代码风格**
- **命名规范**:
  - 类名：PascalCase（如`UploadHistory`）
  - 函数名：snake_case（如`upload_file`）
  - 常量：UPPER_SNAKE_CASE（如`MAX_FILE_SIZE`）
- **类型提示**: 使用Python类型注解
  ```python
  async def upload_file(
      file_content: bytes,
      file_name: str,
      business_id: str
  ) -> Dict[str, Any]:
  ```

### 2. **错误处理**
- 使用`HTTPException`返回HTTP错误
- 业务错误返回统一的错误响应格式
- 记录详细的错误日志

### 3. **异步规范**
- 路由函数使用`async def`
- HTTP请求使用`httpx.AsyncClient`
- 并发控制使用`asyncio.Semaphore`

### 4. **数据库操作**
- 使用参数化查询防止SQL注入
- 及时关闭数据库连接
- 所有时间使用北京时区

### 5. **配置管理**
- 所有配置通过环境变量注入
- 敏感信息不硬编码
- 提供默认值和验证

### 6. **文档规范**
- API使用FastAPI自动文档
- 函数使用docstring说明
- 复杂逻辑添加注释

---

## 新功能集成点

### 异步图片上传功能集成建议

#### 1. **任务队列引入**
**集成点**: `app/core/`

建议添加：
- `app/core/task_queue.py`: 任务队列管理（Celery或RQ）
- `app/core/redis_client.py`: Redis连接管理

**依赖**:
```python
# requirements.txt
celery==5.3.4
redis==5.0.1
```

#### 2. **异步任务定义**
**集成点**: `app/tasks/`（新建目录）

建议文件结构：
```
app/tasks/
├── __init__.py
├── upload_task.py      # 异步上传任务
└── retry_task.py       # 失败重试任务
```

#### 3. **API修改**
**集成点**: `app/api/upload.py`

需要修改：
```python
@router.post("/upload")
async def upload_files(...):
    # 当前: 同步等待上传完成
    # 修改为: 创建异步任务，立即返回任务ID

    task_ids = []
    for file in files:
        task = upload_task.delay(file_content, file_name, ...)
        task_ids.append(task.id)

    return {"task_ids": task_ids, "status": "processing"}
```

#### 4. **任务状态查询API**
**集成点**: `app/api/`（新建路由）

建议添加：
```python
# app/api/tasks.py
@router.get("/tasks/{task_id}")
async def get_task_status(task_id: str):
    task = AsyncResult(task_id)
    return {
        "task_id": task_id,
        "status": task.status,
        "result": task.result
    }
```

#### 5. **数据库扩展**
**集成点**: `app/core/database.py`

建议添加表：
```sql
CREATE TABLE upload_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id VARCHAR(255) UNIQUE NOT NULL,
    business_id VARCHAR(50) NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    status VARCHAR(20) NOT NULL,  -- pending/processing/success/failed
    created_at DATETIME,
    completed_at DATETIME
)
```

#### 6. **前端适配**
**集成点**: `app/static/js/app.js`

需要修改：
```javascript
// 当前: 等待上传完成
// 修改为: 轮询任务状态

async function uploadFiles() {
    const response = await fetch('/api/upload', {...});
    const {task_ids} = await response.json();

    // 轮询任务状态
    for (const task_id of task_ids) {
        pollTaskStatus(task_id);
    }
}

function pollTaskStatus(task_id) {
    const interval = setInterval(async () => {
        const response = await fetch(`/api/tasks/${task_id}`);
        const {status, result} = await response.json();

        if (status === 'success' || status === 'failed') {
            clearInterval(interval);
            updateUI(result);
        }
    }, 2000);
}
```

---

## 潜在约束与考虑因素

### 1. **技术约束**

#### 1.1 **SQLite限制**
- **并发写入**: SQLite在高并发写入时可能出现锁定
- **建议**:
  - 考虑迁移到PostgreSQL或MySQL（生产环境）
  - 或使用WAL模式提升并发性能
  ```python
  conn.execute("PRAGMA journal_mode=WAL")
  ```

#### 1.2 **文件存储**
- **本地存储**: 当前文件存储在本地`data/uploaded_files/`
- **问题**:
  - 单机存储容量限制
  - Docker容器重启可能丢失（需卷挂载）
- **建议**: 考虑对象存储（如AWS S3、阿里云OSS）

#### 1.3 **Token缓存**
- **内存缓存**: 当前Token缓存在内存
- **问题**:
  - 多实例部署时无法共享
  - 重启服务缓存丢失
- **建议**: 使用Redis缓存

### 2. **性能约束**

#### 2.1 **并发限制**
- **当前限制**: 3个并发上传（前后端一致）
- **瓶颈**: 用友云API限流
- **建议**:
  - 引入任务队列，削峰填谷
  - 监控用友云API限流情况

#### 2.2 **文件大小限制**
- **当前限制**: 单文件10MB
- **问题**: 高清图片可能超限
- **建议**:
  - 前端压缩图片（如使用`canvas`）
  - 或增加文件大小限制

#### 2.3 **重试机制**
- **当前策略**: 固定间隔（2秒）重试3次
- **问题**: 短时间内频繁重试可能触发限流
- **建议**: 指数退避（Exponential Backoff）
  ```python
  delay = settings.RETRY_DELAY * (2 ** attempt)
  await asyncio.sleep(delay)
  ```

### 3. **安全约束**

#### 3.1 **CORS配置**
- **当前配置**: 允许所有来源（`allow_origins=["*"]`）
- **风险**: 跨域攻击
- **建议**: 生产环境限制允许的域名
  ```python
  allow_origins=["https://yourdomain.com"]
  ```

#### 3.2 **文件类型验证**
- **当前验证**: 仅检查文件扩展名
- **风险**: 恶意文件伪装为图片
- **建议**: 添加文件内容验证（魔数检查）
  ```python
  # 检查JPEG魔数
  if file_content[:2] != b'\xff\xd8':
      raise HTTPException(status_code=400, detail="无效的JPEG文件")
  ```

#### 3.3 **SQL注入**
- **当前防护**: 使用参数化查询
- **风险**: 动态SQL拼接（如`WHERE {where_sql}`）
- **建议**: 确保所有SQL拼接来自可信源

### 4. **运维约束**

#### 4.1 **日志管理**
- **当前方式**: 输出到控制台
- **问题**: 日志不持久化
- **建议**: 配置日志文件输出
  ```python
  import logging
  logging.basicConfig(
      filename='logs/app.log',
      level=logging.INFO,
      format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
  )
  ```

#### 4.2 **监控告警**
- **当前状态**: 无监控
- **建议**:
  - 添加Prometheus metrics端点
  - 配置Grafana仪表盘
  - 设置告警规则（如上传失败率>10%）

#### 4.3 **备份策略**
- **数据库备份**: 需定期备份`data/uploads.db`
- **文件备份**: 需定期备份`data/uploaded_files/`
- **建议**: 配置自动备份脚本

### 5. **业务约束**

#### 5.1 **用友云API依赖**
- **问题**: 用友云服务不可用时，系统完全不可用
- **建议**:
  - 引入任务队列，失败任务延迟重试
  - 提供降级方案（仅保存到本地）

#### 5.2 **单据编号格式**
- **当前验证**: 仅检查非空
- **问题**: 不同业务类型可能有不同格式要求
- **建议**: 添加格式验证规则

#### 5.3 **历史记录保留**
- **当前策略**: 永久保留（软删除）
- **问题**: 数据库膨胀
- **建议**: 定期归档或硬删除旧记录

---

## 总结

### 项目优势

1. **技术选型合理**
   - FastAPI提供高性能和现代化开发体验
   - 异步IO充分利用系统资源
   - SQLite简化部署和维护

2. **代码质量高**
   - 模块化设计，职责清晰
   - 完善的测试覆盖
   - 详细的代码注释和文档

3. **用户体验好**
   - 移动端友好的界面
   - 二维码快速访问
   - 实时进度反馈
   - 完善的错误提示

4. **运维友好**
   - Docker一键部署
   - 健康检查支持
   - 详细的部署文档

### 改进方向（用于异步上传功能）

1. **引入任务队列**
   - 解耦上传请求和实际上传
   - 提升系统响应速度
   - 支持失败重试和优先级控制

2. **优化存储方案**
   - 考虑对象存储（S3/OSS）
   - 迁移到关系型数据库（PostgreSQL）
   - 使用Redis缓存

3. **增强监控能力**
   - 添加Metrics端点
   - 配置日志聚合
   - 设置告警规则

4. **提升安全性**
   - 添加身份认证
   - 限流保护
   - 文件内容验证

---

## 附录

### A. 关键文件清单

#### 核心业务逻辑
- `app/api/upload.py`: 文件上传核心逻辑（450行）
- `app/core/yonyou_client.py`: 用友云API客户端（150行）
- `app/core/database.py`: 数据库操作（110行）

#### 配置与启动
- `app/core/config.py`: 配置管理（66行）
- `app/main.py`: FastAPI应用入口（90行）
- `run.py`: 启动脚本（14行）

#### 前端资源
- `app/static/js/app.js`: 上传页面逻辑（600行）
- `app/static/js/admin.js`: 管理页面逻辑（650行）
- `app/static/index.html`: 上传页面（120行）
- `app/static/admin.html`: 管理页面（200行）

### B. API端点清单

#### 上传相关
- `POST /api/upload`: 批量上传文件
- `GET /api/history/{business_id}`: 查询上传历史

#### 管理后台
- `GET /api/admin/records`: 分页查询记录
- `GET /api/admin/export`: 导出ZIP包
- `GET /api/admin/statistics`: 统计数据
- `DELETE /api/admin/records`: 软删除记录

#### 系统
- `GET /api/health`: 健康检查
- `GET /`: 上传页面
- `GET /admin`: 管理页面

### C. 环境变量清单

| 变量名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `APP_NAME` | string | 单据上传管理系统 | 应用名称 |
| `APP_VERSION` | string | 1.0.0 | 应用版本 |
| `HOST` | string | 0.0.0.0 | 监听地址 |
| `PORT` | int | 10000 | 监听端口 |
| `DEBUG` | bool | false | 调试模式 |
| `YONYOU_APP_KEY` | string | 必需 | 用友云AppKey |
| `YONYOU_APP_SECRET` | string | 必需 | 用友云AppSecret |
| `YONYOU_BUSINESS_TYPE` | string | yonbip-scm-scmsa | 业务类型 |
| `MAX_FILE_SIZE` | int | 10485760 | 单文件最大大小（字节） |
| `MAX_FILES_PER_REQUEST` | int | 10 | 单次最大文件数 |
| `MAX_RETRY_COUNT` | int | 3 | 最大重试次数 |
| `RETRY_DELAY` | int | 2 | 重试延迟（秒） |
| `MAX_CONCURRENT_UPLOADS` | int | 3 | 最大并发上传数 |
| `DATABASE_URL` | string | sqlite:///data/uploads.db | 数据库URL |
| `LOCAL_STORAGE_PATH` | string | data/uploaded_files | 本地存储路径 |

### D. 依赖版本清单

```
fastapi==0.104.1
uvicorn[standard]==0.24.0
python-multipart==0.0.6
httpx==0.25.1
pydantic==2.5.0
pydantic-settings==2.1.0
python-dotenv==1.0.0
openpyxl==3.1.2
pytest==7.4.3
pytest-asyncio==0.21.1
pytest-cov==4.1.0
pytest-mock==3.12.0
Pillow==10.1.0
```

---

**报告生成时间**: 2025-10-21
**分析对象**: 单据上传管理系统 v1.0.0
**仓库路径**: /Users/lichuansong/Desktop/projects/单据上传管理
