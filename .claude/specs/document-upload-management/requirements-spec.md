# 单据上传管理系统 - 技术规范文档

**版本**: 1.0.0
**生成日期**: 2025-10-03
**状态**: 实现就绪

---

## 问题陈述

### 业务问题
仓库工作人员需要将单据照片上传到用友云平台并关联到指定业务单据，当前缺乏便捷的移动端上传工具，导致：
- 无法快速通过扫码关联单据
- 移动端拍照上传体验差
- 缺少上传历史追溯机制
- 上传失败时无法有效重试

### 当前状态
项目处于早期阶段，仅有API文档，无现有代码库。

### 期望结果
构建一个轻量级的Web应用，支持：
1. 扫描二维码跳转到上传页面 (URL格式: `http://{IP}:10000/{businessId}`)
2. 移动端友好的图片选择和上传界面 (支持相册/拍照)
3. 批量上传最多10张图片，显示实时进度
4. 自动调用用友云API上传文件并关联业务单据
5. 本地SQLite数据库记录所有上传历史
6. 失败重试机制和详细错误提示

---

## 解决方案概述

### 核心策略
采用前后端分离的架构：
- **前端**: 纯HTML/CSS/JavaScript (无构建工具)，移动端优先响应式设计
- **后端**: Python + FastAPI作为API网关，处理Token管理和文件转发
- **数据库**: SQLite存储上传历史记录
- **部署**: 单机部署在10000端口，支持局域网访问

### 核心变更
1. 创建FastAPI后端服务处理Token认证和文件代理上传
2. 创建移动端优化的HTML上传页面
3. 实现SQLite数据库记录上传历史
4. 实现HMAC-SHA256签名算法获取用友云Token
5. 实现带重试机制的文件上传流程

### 成功标准
- 扫码后1秒内加载上传页面
- 单张图片上传成功率 >95%
- 10张图片并发上传时间 <30秒
- 所有上传记录可追溯查询
- 失败时显示清晰的错误信息和重试选项

---

## 技术实现

### 1. 项目结构

```
/Users/lichuansong/Desktop/projects/单据上传管理/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI应用入口
│   ├── api/
│   │   ├── __init__.py
│   │   ├── upload.py           # 上传相关API端点
│   │   └── history.py          # 历史记录API端点
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py           # 配置管理
│   │   ├── database.py         # 数据库连接
│   │   └── yonyou_client.py    # 用友云API客户端
│   ├── models/
│   │   ├── __init__.py
│   │   └── upload_history.py   # 数据模型
│   └── static/
│       ├── index.html          # 上传页面
│       ├── css/
│       │   └── style.css       # 样式文件
│       └── js/
│           └── app.js          # 前端逻辑
├── data/
│   └── uploads.db              # SQLite数据库
├── logs/                       # 日志目录
├── .env                        # 环境变量配置
├── .env.example                # 环境变量示例
├── requirements.txt            # Python依赖
├── run.py                      # 启动脚本
└── README.md                   # 项目说明
```

### 2. 数据库设计

#### 数据库Schema (SQLite)

```sql
-- 上传历史记录表
CREATE TABLE IF NOT EXISTS upload_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_id VARCHAR(50) NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    file_size INTEGER NOT NULL,
    file_extension VARCHAR(20),
    upload_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) NOT NULL,  -- 'success', 'failed', 'pending'
    error_code VARCHAR(50),
    error_message TEXT,
    yonyou_file_id VARCHAR(255),
    retry_count INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_business_id ON upload_history(business_id);
CREATE INDEX IF NOT EXISTS idx_upload_time ON upload_history(upload_time);
CREATE INDEX IF NOT EXISTS idx_status ON upload_history(status);

-- Token缓存表
CREATE TABLE IF NOT EXISTS token_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    access_token TEXT NOT NULL,
    expires_at DATETIME NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

#### 数据模型定义

**UploadHistory Model** (`app/models/upload_history.py`):
```python
from datetime import datetime
from typing import Optional

class UploadHistory:
    def __init__(
        self,
        id: Optional[int] = None,
        business_id: str = "",
        file_name: str = "",
        file_size: int = 0,
        file_extension: str = "",
        upload_time: Optional[datetime] = None,
        status: str = "pending",
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
        yonyou_file_id: Optional[str] = None,
        retry_count: int = 0
    ):
        self.id = id
        self.business_id = business_id
        self.file_name = file_name
        self.file_size = file_size
        self.file_extension = file_extension
        self.upload_time = upload_time or datetime.now()
        self.status = status
        self.error_code = error_code
        self.error_message = error_message
        self.yonyou_file_id = yonyou_file_id
        self.retry_count = retry_count
```

### 3. 后端API详细设计

#### 3.1 配置管理 (`app/core/config.py`)

```python
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # 应用配置
    APP_NAME: str = "单据上传管理系统"
    APP_VERSION: str = "1.0.0"
    HOST: str = "0.0.0.0"
    PORT: int = 10000
    DEBUG: bool = False

    # 用友云配置
    YONYOU_APP_KEY: str = "2b2c5f61d8734cd49e76f8f918977c5d"
    YONYOU_APP_SECRET: str = "61bc68be07201201142a8bf751a59068df9833e1"
    YONYOU_BUSINESS_TYPE: str = "onbip-scm-scmsa"
    YONYOU_AUTH_URL: str = "https://c4.yonyoucloud.com/iuap-api-auth/open-auth/selfAppAuth/base/v1/getAccessToken"
    YONYOU_UPLOAD_URL: str = "https://c4.yonyoucloud.com/iuap-api-gateway/yonbip/uspace/iuap-apcom-file/rest/v1/file"

    # 上传配置
    MAX_FILE_SIZE: int = 10 * 1024 * 1024  # 10MB
    MAX_FILES_PER_REQUEST: int = 10
    ALLOWED_EXTENSIONS: set = {".jpg", ".jpeg", ".png", ".gif"}

    # 重试配置
    MAX_RETRY_COUNT: int = 3
    RETRY_DELAY: int = 2  # 秒
    REQUEST_TIMEOUT: int = 30  # 秒

    # 并发控制
    MAX_CONCURRENT_UPLOADS: int = 3

    # 数据库配置
    DATABASE_URL: str = "sqlite:///data/uploads.db"

    # Token缓存配置
    TOKEN_CACHE_DURATION: int = 3600  # 1小时，实际应根据用友云返回的expires_in设置

    class Config:
        env_file = ".env"
        case_sensitive = True

@lru_cache()
def get_settings():
    return Settings()
```

#### 3.2 用友云API客户端 (`app/core/yonyou_client.py`)

```python
import hmac
import hashlib
import base64
import time
import urllib.parse
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import httpx
from app.core.config import get_settings

settings = get_settings()

class YonYouClient:
    def __init__(self):
        self.app_key = settings.YONYOU_APP_KEY
        self.app_secret = settings.YONYOU_APP_SECRET
        self.auth_url = settings.YONYOU_AUTH_URL
        self.upload_url = settings.YONYOU_UPLOAD_URL
        self.business_type = settings.YONYOU_BUSINESS_TYPE
        self._token_cache: Optional[Dict[str, Any]] = None

    def _generate_signature(self, timestamp: str) -> str:
        """生成HMAC-SHA256签名"""
        # 构建待签名字符串: appKey{appKey}timestamp{timestamp}
        string_to_sign = f"appKey{self.app_key}timestamp{timestamp}"

        # 使用HMAC-SHA256计算签名
        hmac_code = hmac.new(
            self.app_secret.encode(),
            string_to_sign.encode(),
            hashlib.sha256
        ).digest()

        # Base64编码并URL编码
        signature = urllib.parse.quote(base64.b64encode(hmac_code).decode())

        return signature

    async def get_access_token(self, force_refresh: bool = False) -> str:
        """获取access_token，支持缓存"""
        # 检查缓存
        if not force_refresh and self._token_cache:
            if datetime.now() < self._token_cache["expires_at"]:
                return self._token_cache["access_token"]

        # 生成时间戳(毫秒)
        timestamp = str(int(time.time() * 1000))

        # 生成签名
        signature = self._generate_signature(timestamp)

        # 构建请求URL
        url = f"{self.auth_url}?appKey={self.app_key}&timestamp={timestamp}&signature={signature}"

        # 发送请求
        async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT) as client:
            response = await client.get(url)
            result = response.json()

        # 检查响应
        if result.get("code") == "00000":
            access_token = result["data"]["access_token"]
            expires_in = result["data"].get("expires_in", 3600)  # 默认1小时

            # 缓存token
            self._token_cache = {
                "access_token": access_token,
                "expires_at": datetime.now() + timedelta(seconds=expires_in - 60)  # 提前60秒过期
            }

            return access_token
        else:
            raise Exception(f"获取Token失败: {result.get('message', '未知错误')}")

    async def upload_file(
        self,
        file_content: bytes,
        file_name: str,
        business_id: str,
        retry_count: int = 0
    ) -> Dict[str, Any]:
        """上传文件到用友云"""
        try:
            # 获取access_token
            access_token = await self.get_access_token()

            # 构建请求URL
            url = f"{self.upload_url}?access_token={access_token}&businessType={self.business_type}&businessId={business_id}"

            # 构建multipart/form-data请求
            files = {
                "files": (file_name, file_content, "application/octet-stream")
            }

            # 发送请求
            async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT) as client:
                response = await client.post(url, files=files)
                result = response.json()

            # 检查响应
            if result.get("code") == "200":
                return {
                    "success": True,
                    "data": result["data"]["data"][0]
                }
            else:
                # 特殊处理: Token过期时自动刷新重试
                if result.get("code") == 1090003500065 and retry_count == 0:
                    access_token = await self.get_access_token(force_refresh=True)
                    return await self.upload_file(file_content, file_name, business_id, retry_count + 1)

                return {
                    "success": False,
                    "error_code": str(result.get("code")),
                    "error_message": result.get("message", "未知错误")
                }

        except Exception as e:
            return {
                "success": False,
                "error_code": "NETWORK_ERROR",
                "error_message": str(e)
            }
```

#### 3.3 API路由定义

**主应用入口** (`app/main.py`):
```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import get_settings
from app.core.database import init_database
from app.api import upload, history

settings = get_settings()

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION
)

# CORS配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静态文件
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# 路由
app.include_router(upload.router, prefix="/api", tags=["upload"])
app.include_router(history.router, prefix="/api", tags=["history"])

# 启动事件
@app.on_event("startup")
async def startup_event():
    init_database()

# 根路由 - 重定向到上传页面
@app.get("/{business_id}")
async def upload_page(business_id: str):
    from fastapi.responses import FileResponse
    return FileResponse("app/static/index.html")
```

**上传API** (`app/api/upload.py`):
```python
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from typing import List
import asyncio
from datetime import datetime
from app.core.config import get_settings
from app.core.yonyou_client import YonYouClient
from app.core.database import get_db_connection
from app.models.upload_history import UploadHistory

router = APIRouter()
settings = get_settings()
yonyou_client = YonYouClient()

@router.post("/upload")
async def upload_files(
    business_id: str = Form(...),
    files: List[UploadFile] = File(...)
):
    """
    批量上传文件到用友云

    请求参数:
    - business_id: 业务单据ID
    - files: 文件列表 (最多10个)

    响应格式:
    {
        "success": true,
        "total": 10,
        "succeeded": 9,
        "failed": 1,
        "results": [
            {
                "file_name": "image1.jpg",
                "success": true,
                "file_id": "xxx",
                "file_size": 123456
            },
            {
                "file_name": "image2.jpg",
                "success": false,
                "error_code": "1090003500065",
                "error_message": "上传信息未包含租户及用户信息"
            }
        ]
    }
    """
    # 验证businessId格式
    if not business_id or len(business_id) != 6 or not business_id.isdigit():
        raise HTTPException(status_code=400, detail="businessId必须为6位数字")

    # 验证文件数量
    if len(files) > settings.MAX_FILES_PER_REQUEST:
        raise HTTPException(status_code=400, detail=f"单次最多上传{settings.MAX_FILES_PER_REQUEST}个文件")

    # 验证文件
    for file in files:
        # 检查文件扩展名
        file_ext = "." + file.filename.split(".")[-1].lower()
        if file_ext not in settings.ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的文件格式: {file_ext}，支持的格式: {', '.join(settings.ALLOWED_EXTENSIONS)}"
            )

    # 并发上传（限制并发数为3）
    semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_UPLOADS)

    async def upload_single_file(upload_file: UploadFile):
        async with semaphore:
            # 读取文件内容
            file_content = await upload_file.read()
            file_size = len(file_content)

            # 验证文件大小
            if file_size > settings.MAX_FILE_SIZE:
                return {
                    "file_name": upload_file.filename,
                    "success": False,
                    "error_code": "FILE_TOO_LARGE",
                    "error_message": f"文件大小超过{settings.MAX_FILE_SIZE / 1024 / 1024}MB限制"
                }

            # 创建上传历史记录
            history = UploadHistory(
                business_id=business_id,
                file_name=upload_file.filename,
                file_size=file_size,
                file_extension="." + upload_file.filename.split(".")[-1].lower(),
                status="pending"
            )

            # 上传到用友云（带重试）
            for attempt in range(settings.MAX_RETRY_COUNT):
                result = await yonyou_client.upload_file(
                    file_content,
                    upload_file.filename,
                    business_id
                )

                if result["success"]:
                    # 更新历史记录
                    history.status = "success"
                    history.yonyou_file_id = result["data"]["id"]
                    history.retry_count = attempt

                    # 保存到数据库
                    save_upload_history(history)

                    return {
                        "file_name": upload_file.filename,
                        "success": True,
                        "file_id": result["data"]["id"],
                        "file_size": file_size,
                        "file_extension": result["data"]["fileExtension"]
                    }
                else:
                    if attempt < settings.MAX_RETRY_COUNT - 1:
                        await asyncio.sleep(settings.RETRY_DELAY)
                    else:
                        # 最后一次失败
                        history.status = "failed"
                        history.error_code = result["error_code"]
                        history.error_message = result["error_message"]
                        history.retry_count = attempt

                        # 保存到数据库
                        save_upload_history(history)

                        return {
                            "file_name": upload_file.filename,
                            "success": False,
                            "error_code": result["error_code"],
                            "error_message": result["error_message"]
                        }

    # 并发执行上传
    results = await asyncio.gather(*[upload_single_file(f) for f in files])

    # 统计结果
    succeeded = sum(1 for r in results if r["success"])
    failed = len(results) - succeeded

    return {
        "success": True,
        "total": len(files),
        "succeeded": succeeded,
        "failed": failed,
        "results": results
    }

def save_upload_history(history: UploadHistory):
    """保存上传历史到数据库"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO upload_history
        (business_id, file_name, file_size, file_extension, status,
         error_code, error_message, yonyou_file_id, retry_count)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        history.business_id,
        history.file_name,
        history.file_size,
        history.file_extension,
        history.status,
        history.error_code,
        history.error_message,
        history.yonyou_file_id,
        history.retry_count
    ))

    conn.commit()
    conn.close()
```

**历史记录API** (`app/api/history.py`):
```python
from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
from app.core.database import get_db_connection

router = APIRouter()

@router.get("/history/{business_id}")
async def get_upload_history(business_id: str) -> Dict[str, Any]:
    """
    查询指定业务单据的上传历史

    响应格式:
    {
        "business_id": "000000",
        "total_count": 15,
        "success_count": 14,
        "failed_count": 1,
        "records": [
            {
                "id": 1,
                "file_name": "image1.jpg",
                "file_size": 123456,
                "upload_time": "2025-10-03 10:30:00",
                "status": "success",
                "yonyou_file_id": "xxx"
            }
        ]
    }
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # 查询记录
    cursor.execute("""
        SELECT id, file_name, file_size, file_extension, upload_time,
               status, error_code, error_message, yonyou_file_id, retry_count
        FROM upload_history
        WHERE business_id = ?
        ORDER BY upload_time DESC
    """, (business_id,))

    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return {
            "business_id": business_id,
            "total_count": 0,
            "success_count": 0,
            "failed_count": 0,
            "records": []
        }

    # 转换为字典列表
    records = []
    success_count = 0
    failed_count = 0

    for row in rows:
        record = {
            "id": row[0],
            "file_name": row[1],
            "file_size": row[2],
            "file_extension": row[3],
            "upload_time": row[4],
            "status": row[5],
            "error_code": row[6],
            "error_message": row[7],
            "yonyou_file_id": row[8],
            "retry_count": row[9]
        }
        records.append(record)

        if row[5] == "success":
            success_count += 1
        else:
            failed_count += 1

    return {
        "business_id": business_id,
        "total_count": len(records),
        "success_count": success_count,
        "failed_count": failed_count,
        "records": records
    }
```

#### 3.4 数据库管理 (`app/core/database.py`)

```python
import sqlite3
import os
from app.core.config import get_settings

settings = get_settings()

def get_db_connection():
    """获取数据库连接"""
    db_path = settings.DATABASE_URL.replace("sqlite:///", "")
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_database():
    """初始化数据库"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # 创建上传历史表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS upload_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id VARCHAR(50) NOT NULL,
            file_name VARCHAR(255) NOT NULL,
            file_size INTEGER NOT NULL,
            file_extension VARCHAR(20),
            upload_time DATETIME DEFAULT CURRENT_TIMESTAMP,
            status VARCHAR(20) NOT NULL,
            error_code VARCHAR(50),
            error_message TEXT,
            yonyou_file_id VARCHAR(255),
            retry_count INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 创建索引
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_business_id
        ON upload_history(business_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_upload_time
        ON upload_history(upload_time)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_status
        ON upload_history(status)
    """)

    conn.commit()
    conn.close()
```

### 4. 前端设计

#### 4.1 HTML结构 (`app/static/index.html`)

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <title>单据上传 - 用友云</title>
    <link rel="stylesheet" href="/static/css/style.css">
</head>
<body>
    <div class="container">
        <!-- 头部 -->
        <header class="header">
            <h1>单据上传</h1>
            <p class="business-id">业务单据号: <span id="businessIdDisplay">--</span></p>
        </header>

        <!-- 上传区域 -->
        <div class="upload-section">
            <div class="upload-area" id="uploadArea">
                <input type="file" id="fileInput" accept="image/*" multiple style="display: none;">
                <div class="upload-icon">📷</div>
                <p>点击选择图片或拍照</p>
                <p class="hint">支持jpg、png、gif格式，单张最大10MB，最多10张</p>
            </div>
        </div>

        <!-- 图片预览区域 -->
        <div class="preview-section" id="previewSection" style="display: none;">
            <div class="preview-header">
                <span>已选择 <span id="selectedCount">0</span>/10 张</span>
                <button class="btn-clear" id="btnClear">清空</button>
            </div>
            <div class="preview-list" id="previewList"></div>
        </div>

        <!-- 上传按钮 -->
        <div class="action-section">
            <button class="btn-upload" id="btnUpload" disabled>开始上传</button>
        </div>

        <!-- 进度区域 -->
        <div class="progress-section" id="progressSection" style="display: none;">
            <div class="progress-header">
                <span>上传进度</span>
                <span id="progressText">0/0</span>
            </div>
            <div class="progress-bar-container">
                <div class="progress-bar" id="progressBar"></div>
            </div>
            <div class="progress-list" id="progressList"></div>
        </div>

        <!-- 结果提示 -->
        <div class="toast" id="toast"></div>

        <!-- 历史记录按钮 -->
        <div class="history-section">
            <button class="btn-history" id="btnHistory">查看上传历史</button>
        </div>
    </div>

    <!-- 历史记录弹窗 -->
    <div class="modal" id="historyModal" style="display: none;">
        <div class="modal-content">
            <div class="modal-header">
                <h2>上传历史</h2>
                <button class="btn-close" id="btnCloseModal">×</button>
            </div>
            <div class="modal-body" id="historyList"></div>
        </div>
    </div>

    <script src="/static/js/app.js"></script>
</body>
</html>
```

#### 4.2 CSS样式 (`app/static/css/style.css`)

```css
/* 基础样式重置 */
* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
    background: #f5f5f5;
    color: #333;
    line-height: 1.6;
}

.container {
    max-width: 600px;
    margin: 0 auto;
    padding: 20px;
    background: #fff;
    min-height: 100vh;
}

/* 头部 */
.header {
    text-align: center;
    padding: 20px 0;
    border-bottom: 1px solid #eee;
}

.header h1 {
    font-size: 24px;
    color: #1890ff;
    margin-bottom: 10px;
}

.business-id {
    font-size: 14px;
    color: #666;
}

.business-id span {
    font-weight: bold;
    color: #1890ff;
}

/* 上传区域 */
.upload-section {
    margin: 30px 0;
}

.upload-area {
    border: 2px dashed #d9d9d9;
    border-radius: 8px;
    padding: 40px 20px;
    text-align: center;
    cursor: pointer;
    transition: all 0.3s;
}

.upload-area:hover {
    border-color: #1890ff;
    background: #f0f8ff;
}

.upload-icon {
    font-size: 48px;
    margin-bottom: 10px;
}

.upload-area p {
    font-size: 16px;
    color: #666;
    margin-bottom: 5px;
}

.upload-area .hint {
    font-size: 12px;
    color: #999;
}

/* 预览区域 */
.preview-section {
    margin: 20px 0;
}

.preview-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 10px 0;
    font-size: 14px;
    color: #666;
}

.btn-clear {
    background: none;
    border: none;
    color: #ff4d4f;
    cursor: pointer;
    font-size: 14px;
}

.preview-list {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(100px, 1fr));
    gap: 10px;
}

.preview-item {
    position: relative;
    padding-top: 100%;
    border-radius: 8px;
    overflow: hidden;
    border: 1px solid #eee;
}

.preview-item img {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    object-fit: cover;
}

.preview-item .btn-remove {
    position: absolute;
    top: 5px;
    right: 5px;
    width: 24px;
    height: 24px;
    border-radius: 50%;
    background: rgba(0, 0, 0, 0.6);
    color: #fff;
    border: none;
    font-size: 16px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
}

/* 操作按钮 */
.action-section {
    margin: 20px 0;
}

.btn-upload {
    width: 100%;
    padding: 15px;
    font-size: 16px;
    font-weight: bold;
    color: #fff;
    background: #1890ff;
    border: none;
    border-radius: 8px;
    cursor: pointer;
    transition: all 0.3s;
}

.btn-upload:hover:not(:disabled) {
    background: #40a9ff;
}

.btn-upload:disabled {
    background: #d9d9d9;
    cursor: not-allowed;
}

/* 进度区域 */
.progress-section {
    margin: 20px 0;
}

.progress-header {
    display: flex;
    justify-content: space-between;
    padding: 10px 0;
    font-size: 14px;
    color: #666;
}

.progress-bar-container {
    height: 10px;
    background: #f0f0f0;
    border-radius: 5px;
    overflow: hidden;
    margin-bottom: 15px;
}

.progress-bar {
    height: 100%;
    background: linear-gradient(90deg, #1890ff, #40a9ff);
    transition: width 0.3s;
    width: 0;
}

.progress-list {
    font-size: 12px;
}

.progress-item {
    display: flex;
    align-items: center;
    padding: 8px 0;
    border-bottom: 1px solid #f0f0f0;
}

.progress-item .filename {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.progress-item .status {
    margin-left: 10px;
    font-size: 18px;
}

.progress-item .status.success {
    color: #52c41a;
}

.progress-item .status.error {
    color: #ff4d4f;
}

.progress-item .status.loading {
    color: #1890ff;
}

.progress-item .error-msg {
    font-size: 11px;
    color: #ff4d4f;
    margin-top: 3px;
}

/* Toast提示 */
.toast {
    position: fixed;
    top: 20px;
    left: 50%;
    transform: translateX(-50%);
    padding: 12px 24px;
    background: rgba(0, 0, 0, 0.8);
    color: #fff;
    border-radius: 4px;
    font-size: 14px;
    z-index: 9999;
    display: none;
    animation: slideDown 0.3s;
}

@keyframes slideDown {
    from {
        opacity: 0;
        transform: translateX(-50%) translateY(-20px);
    }
    to {
        opacity: 1;
        transform: translateX(-50%) translateY(0);
    }
}

.toast.success {
    background: #52c41a;
}

.toast.error {
    background: #ff4d4f;
}

/* 历史记录按钮 */
.history-section {
    margin: 30px 0;
    text-align: center;
}

.btn-history {
    padding: 10px 30px;
    font-size: 14px;
    color: #1890ff;
    background: #fff;
    border: 1px solid #1890ff;
    border-radius: 4px;
    cursor: pointer;
    transition: all 0.3s;
}

.btn-history:hover {
    background: #f0f8ff;
}

/* 弹窗 */
.modal {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.5);
    z-index: 10000;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 20px;
}

.modal-content {
    background: #fff;
    border-radius: 8px;
    max-width: 600px;
    width: 100%;
    max-height: 80vh;
    display: flex;
    flex-direction: column;
}

.modal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 20px;
    border-bottom: 1px solid #eee;
}

.modal-header h2 {
    font-size: 18px;
}

.btn-close {
    width: 32px;
    height: 32px;
    border: none;
    background: none;
    font-size: 28px;
    cursor: pointer;
    color: #999;
}

.modal-body {
    padding: 20px;
    overflow-y: auto;
}

.history-item {
    padding: 15px;
    border: 1px solid #eee;
    border-radius: 8px;
    margin-bottom: 10px;
}

.history-item .filename {
    font-weight: bold;
    margin-bottom: 5px;
}

.history-item .meta {
    font-size: 12px;
    color: #999;
}

.history-item .status-badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 12px;
    margin-left: 10px;
}

.history-item .status-badge.success {
    background: #f6ffed;
    color: #52c41a;
}

.history-item .status-badge.failed {
    background: #fff1f0;
    color: #ff4d4f;
}

/* 响应式 */
@media (max-width: 768px) {
    .container {
        padding: 10px;
    }

    .header h1 {
        font-size: 20px;
    }

    .preview-list {
        grid-template-columns: repeat(auto-fill, minmax(80px, 1fr));
    }
}
```

#### 4.3 JavaScript逻辑 (`app/static/js/app.js`)

```javascript
// 全局状态
const state = {
    businessId: '',
    selectedFiles: [],
    maxFiles: 10,
    maxFileSize: 10 * 1024 * 1024, // 10MB
    uploading: false
};

// DOM元素
const elements = {
    businessIdDisplay: document.getElementById('businessIdDisplay'),
    uploadArea: document.getElementById('uploadArea'),
    fileInput: document.getElementById('fileInput'),
    previewSection: document.getElementById('previewSection'),
    previewList: document.getElementById('previewList'),
    selectedCount: document.getElementById('selectedCount'),
    btnClear: document.getElementById('btnClear'),
    btnUpload: document.getElementById('btnUpload'),
    progressSection: document.getElementById('progressSection'),
    progressBar: document.getElementById('progressBar'),
    progressText: document.getElementById('progressText'),
    progressList: document.getElementById('progressList'),
    toast: document.getElementById('toast'),
    btnHistory: document.getElementById('btnHistory'),
    historyModal: document.getElementById('historyModal'),
    historyList: document.getElementById('historyList'),
    btnCloseModal: document.getElementById('btnCloseModal')
};

// 初始化
function init() {
    // 从URL提取businessId
    const path = window.location.pathname;
    state.businessId = path.substring(1);

    // 验证businessId
    if (!state.businessId || state.businessId.length !== 6 || !/^\d+$/.test(state.businessId)) {
        showToast('错误的业务单据号，请扫描正确的二维码', 'error');
        return;
    }

    elements.businessIdDisplay.textContent = state.businessId;

    // 绑定事件
    elements.uploadArea.addEventListener('click', () => elements.fileInput.click());
    elements.fileInput.addEventListener('change', handleFileSelect);
    elements.btnClear.addEventListener('click', clearFiles);
    elements.btnUpload.addEventListener('click', uploadFiles);
    elements.btnHistory.addEventListener('click', showHistory);
    elements.btnCloseModal.addEventListener('click', () => elements.historyModal.style.display = 'none');
}

// 文件选择处理
function handleFileSelect(e) {
    const files = Array.from(e.target.files);

    // 验证文件数量
    if (state.selectedFiles.length + files.length > state.maxFiles) {
        showToast(`最多只能选择${state.maxFiles}张图片`, 'error');
        return;
    }

    // 验证文件
    for (const file of files) {
        // 检查文件类型
        if (!file.type.startsWith('image/')) {
            showToast(`${file.name} 不是图片文件`, 'error');
            continue;
        }

        // 检查文件大小
        if (file.size > state.maxFileSize) {
            showToast(`${file.name} 超过10MB限制`, 'error');
            continue;
        }

        state.selectedFiles.push(file);
    }

    // 重置input
    e.target.value = '';

    // 更新预览
    updatePreview();
}

// 更新预览
function updatePreview() {
    if (state.selectedFiles.length === 0) {
        elements.previewSection.style.display = 'none';
        elements.btnUpload.disabled = true;
        return;
    }

    elements.previewSection.style.display = 'block';
    elements.btnUpload.disabled = false;
    elements.selectedCount.textContent = state.selectedFiles.length;

    // 清空预览列表
    elements.previewList.innerHTML = '';

    // 生成预览
    state.selectedFiles.forEach((file, index) => {
        const reader = new FileReader();
        reader.onload = (e) => {
            const item = document.createElement('div');
            item.className = 'preview-item';
            item.innerHTML = `
                <img src="${e.target.result}" alt="${file.name}">
                <button class="btn-remove" onclick="removeFile(${index})">×</button>
            `;
            elements.previewList.appendChild(item);
        };
        reader.readAsDataURL(file);
    });
}

// 移除文件
function removeFile(index) {
    state.selectedFiles.splice(index, 1);
    updatePreview();
}

// 清空文件
function clearFiles() {
    state.selectedFiles = [];
    updatePreview();
}

// 上传文件
async function uploadFiles() {
    if (state.uploading || state.selectedFiles.length === 0) {
        return;
    }

    state.uploading = true;
    elements.btnUpload.disabled = true;
    elements.progressSection.style.display = 'block';
    elements.progressList.innerHTML = '';

    // 准备FormData
    const formData = new FormData();
    formData.append('business_id', state.businessId);
    state.selectedFiles.forEach(file => {
        formData.append('files', file);
    });

    // 创建进度项
    state.selectedFiles.forEach(file => {
        const item = document.createElement('div');
        item.className = 'progress-item';
        item.innerHTML = `
            <div class="filename">${file.name}</div>
            <div class="status loading">⏳</div>
        `;
        elements.progressList.appendChild(item);
    });

    try {
        // 发送请求
        const response = await fetch('/api/upload', {
            method: 'POST',
            body: formData
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.detail || '上传失败');
        }

        // 更新进度
        const progressItems = elements.progressList.querySelectorAll('.progress-item');
        result.results.forEach((item, index) => {
            const statusEl = progressItems[index].querySelector('.status');

            if (item.success) {
                statusEl.textContent = '✓';
                statusEl.className = 'status success';
            } else {
                statusEl.textContent = '✗';
                statusEl.className = 'status error';

                // 显示错误信息
                const errorMsg = document.createElement('div');
                errorMsg.className = 'error-msg';
                errorMsg.textContent = item.error_message || '上传失败';
                progressItems[index].appendChild(errorMsg);
            }
        });

        // 更新总进度
        const percent = Math.round((result.succeeded / result.total) * 100);
        elements.progressBar.style.width = `${percent}%`;
        elements.progressText.textContent = `${result.succeeded}/${result.total}`;

        // 显示结果提示
        if (result.failed === 0) {
            showToast(`全部上传成功！`, 'success');

            // 3秒后清空
            setTimeout(() => {
                clearFiles();
                elements.progressSection.style.display = 'none';
            }, 3000);
        } else {
            showToast(`上传完成，成功${result.succeeded}个，失败${result.failed}个`, 'error');
        }

    } catch (error) {
        showToast(error.message, 'error');
    } finally {
        state.uploading = false;
        elements.btnUpload.disabled = false;
    }
}

// 显示历史记录
async function showHistory() {
    try {
        const response = await fetch(`/api/history/${state.businessId}`);
        const result = await response.json();

        if (!response.ok) {
            throw new Error('获取历史记录失败');
        }

        // 渲染历史记录
        if (result.total_count === 0) {
            elements.historyList.innerHTML = '<p style="text-align: center; color: #999;">暂无上传记录</p>';
        } else {
            elements.historyList.innerHTML = result.records.map(record => `
                <div class="history-item">
                    <div class="filename">
                        ${record.file_name}
                        <span class="status-badge ${record.status}">
                            ${record.status === 'success' ? '成功' : '失败'}
                        </span>
                    </div>
                    <div class="meta">
                        <div>大小: ${formatFileSize(record.file_size)}</div>
                        <div>时间: ${record.upload_time}</div>
                        ${record.error_message ? `<div style="color: #ff4d4f;">错误: ${record.error_message}</div>` : ''}
                    </div>
                </div>
            `).join('');
        }

        elements.historyModal.style.display = 'flex';

    } catch (error) {
        showToast(error.message, 'error');
    }
}

// 显示Toast
function showToast(message, type = 'success') {
    elements.toast.textContent = message;
    elements.toast.className = `toast ${type}`;
    elements.toast.style.display = 'block';

    setTimeout(() => {
        elements.toast.style.display = 'none';
    }, 3000);
}

// 格式化文件大小
function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1024 / 1024).toFixed(1) + ' MB';
}

// 启动应用
init();
```

### 5. 配置文件

#### 环境变量示例 (`.env.example`)

```bash
# 应用配置
APP_NAME=单据上传管理系统
APP_VERSION=1.0.0
HOST=0.0.0.0
PORT=10000
DEBUG=false

# 用友云配置
YONYOU_APP_KEY=2b2c5f61d8734cd49e76f8f918977c5d
YONYOU_APP_SECRET=61bc68be07201201142a8bf751a59068df9833e1
YONYOU_BUSINESS_TYPE=onbip-scm-scmsa
YONYOU_AUTH_URL=https://c4.yonyoucloud.com/iuap-api-auth/open-auth/selfAppAuth/base/v1/getAccessToken
YONYOU_UPLOAD_URL=https://c4.yonyoucloud.com/iuap-api-gateway/yonbip/uspace/iuap-apcom-file/rest/v1/file

# 上传配置
MAX_FILE_SIZE=10485760
MAX_FILES_PER_REQUEST=10

# 重试配置
MAX_RETRY_COUNT=3
RETRY_DELAY=2
REQUEST_TIMEOUT=30

# 并发控制
MAX_CONCURRENT_UPLOADS=3

# 数据库配置
DATABASE_URL=sqlite:///data/uploads.db

# Token缓存配置
TOKEN_CACHE_DURATION=3600
```

#### Python依赖 (`requirements.txt`)

```
fastapi==0.104.1
uvicorn[standard]==0.24.0
python-multipart==0.0.6
httpx==0.25.1
pydantic==2.5.0
pydantic-settings==2.1.0
python-dotenv==1.0.0
```

#### 启动脚本 (`run.py`)

```python
import uvicorn
from app.core.config import get_settings

settings = get_settings()

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info"
    )
```

---

## 实现顺序

### 第一阶段：基础架构搭建
1. 创建项目目录结构
2. 配置Python虚拟环境和依赖安装
3. 创建配置管理模块 (`app/core/config.py`)
4. 初始化数据库模块 (`app/core/database.py`)
5. 编写数据库初始化SQL并测试

**验证标准**:
- 项目目录完整
- `pip install -r requirements.txt` 成功
- 数据库文件正常创建，表结构正确

### 第二阶段：用友云API集成
1. 实现HMAC-SHA256签名算法
2. 实现Token获取逻辑 (`YonYouClient.get_access_token()`)
3. 实现文件上传逻辑 (`YonYouClient.upload_file()`)
4. 编写单元测试验证Token获取和文件上传

**验证标准**:
- Token获取成功，返回有效的access_token
- 单文件上传成功，返回用友云文件ID
- 错误处理正确，能识别1090003500065错误并重试

### 第三阶段：后端API开发
1. 创建FastAPI应用入口 (`app/main.py`)
2. 实现上传API端点 (`/api/upload`)
3. 实现历史记录API端点 (`/api/history/{business_id}`)
4. 实现根路由重定向 (`/{business_id}`)
5. 配置CORS和静态文件服务

**验证标准**:
- FastAPI服务启动成功，访问 `http://localhost:10000/docs` 显示API文档
- 使用Postman测试上传接口，能成功上传文件
- 历史记录接口返回正确的数据

### 第四阶段：前端界面开发
1. 创建HTML页面结构 (`app/static/index.html`)
2. 编写CSS样式 (`app/static/css/style.css`)
3. 实现文件选择和预览功能
4. 实现上传逻辑和进度显示
5. 实现历史记录查询弹窗

**验证标准**:
- 在移动端浏览器打开 `http://{IP}:10000/123456`，页面正常显示
- 能选择图片并显示预览
- 点击上传后显示进度条和每个文件的状态
- 历史记录弹窗正常显示数据

### 第五阶段：集成测试和优化
1. 端到端测试：扫码→上传→查看历史
2. 并发上传测试（10张图片同时上传）
3. 异常场景测试（网络断开、Token过期、文件超限）
4. 性能优化（Token缓存、数据库索引）
5. 日志记录完善

**验证标准**:
- 完整流程无阻塞
- 10张图片在30秒内上传完成
- 失败重试机制正常工作
- 所有错误都有友好提示

---

## 验证计划

### 单元测试

#### 后端测试 (`tests/test_yonyou_client.py`)
```python
import pytest
from app.core.yonyou_client import YonYouClient

@pytest.mark.asyncio
async def test_get_access_token():
    """测试Token获取"""
    client = YonYouClient()
    token = await client.get_access_token()
    assert token is not None
    assert len(token) > 0

@pytest.mark.asyncio
async def test_upload_file():
    """测试文件上传"""
    client = YonYouClient()

    # 准备测试文件
    test_file_content = b"test image content"
    test_file_name = "test.jpg"
    test_business_id = "123456"

    result = await client.upload_file(
        test_file_content,
        test_file_name,
        test_business_id
    )

    assert result["success"] == True
    assert "data" in result
    assert "id" in result["data"]
```

#### 前端测试 (手动测试清单)
```
[ ] businessId从URL正确提取
[ ] 文件选择器正常工作（相册/拍照）
[ ] 图片预览正常显示
[ ] 文件数量限制生效（最多10张）
[ ] 文件大小限制生效（最大10MB）
[ ] 文件格式验证生效（仅图片）
[ ] 上传按钮状态切换正确
[ ] 进度条更新流畅
[ ] 成功/失败状态显示正确
[ ] 历史记录查询正常
```

### 集成测试

#### E2E测试场景
```
场景1：正常上传流程
1. 扫描二维码打开页面 (businessId=123456)
2. 选择3张图片
3. 查看预览
4. 点击上传
5. 等待上传完成
6. 验证：3张图片全部成功，显示绿色勾

场景2：部分失败场景
1. 打开页面
2. 选择5张图片（其中1张超过10MB）
3. 点击上传
4. 验证：超限图片被拒绝，其他4张成功

场景3：重试机制
1. 模拟网络不稳定
2. 上传5张图片
3. 验证：失败的图片自动重试，最多3次

场景4：并发上传
1. 选择10张图片
2. 点击上传
3. 验证：最多3个并发请求，其余排队
4. 验证：所有图片最终上传完成

场景5：历史记录查询
1. 上传若干图片
2. 点击"查看上传历史"
3. 验证：显示所有上传记录，包括成功和失败
```

### 业务逻辑验证

#### Token管理验证
```
测试1：Token缓存
- 首次调用获取Token
- 10秒内再次调用，验证使用缓存（不发送请求）
- 修改缓存过期时间，验证自动刷新

测试2：Token过期处理
- 设置过期的Token
- 上传文件
- 验证：自动刷新Token并重试上传
```

#### 数据库验证
```
测试1：记录保存
- 上传3张图片（2成功1失败）
- 查询数据库
- 验证：3条记录，状态正确

测试2：历史查询
- 为businessId=123456上传5张图片
- 为businessId=654321上传3张图片
- 查询123456的历史
- 验证：仅返回5条记录
```

---

## 部署说明

### 1. 环境准备

```bash
# 安装Python 3.8+
python3 --version

# 克隆项目（或创建项目目录）
cd /Users/lichuansong/Desktop/projects/单据上传管理

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑.env文件（可选，默认值已配置好）
# 主要确认：
# - YONYOU_APP_KEY
# - YONYOU_APP_SECRET
# - PORT (默认10000)
```

### 3. 初始化数据库

```bash
# 数据库会在首次启动时自动创建
# 也可以手动运行
python -c "from app.core.database import init_database; init_database()"
```

### 4. 启动服务

```bash
# 开发模式（支持热重载）
python run.py

# 生产模式
uvicorn app.main:app --host 0.0.0.0 --port 10000

# 后台运行（Linux/macOS）
nohup uvicorn app.main:app --host 0.0.0.0 --port 10000 > logs/app.log 2>&1 &
```

### 5. 验证部署

```bash
# 检查服务状态
curl http://localhost:10000/docs

# 测试上传页面
# 在浏览器打开: http://{本机IP}:10000/123456
```

### 6. 生成二维码

使用在线工具或命令行生成二维码：
```bash
# 使用qrencode (需要安装)
qrencode -o qrcode.png "http://{本机IP}:10000/123456"

# 或使用在线工具
# https://www.qr-code-generator.com/
# 输入: http://{本机IP}:10000/123456
```

### 7. 防火墙配置

```bash
# macOS
# 系统偏好设置 -> 安全性与隐私 -> 防火墙 -> 允许端口10000

# Linux (iptables)
sudo iptables -A INPUT -p tcp --dport 10000 -j ACCEPT

# Linux (firewalld)
sudo firewall-cmd --permanent --add-port=10000/tcp
sudo firewall-cmd --reload
```

---

## 安全考虑

### 1. 凭证管理
- **禁止硬编码**: AppKey和AppSecret必须存储在`.env`文件
- **Git忽略**: `.env`文件必须添加到`.gitignore`
- **环境隔离**: 开发和生产环境使用不同的凭证

### 2. Token安全
- Token在内存中缓存，不持久化到磁盘
- Token过期前60秒自动刷新
- 每次请求前验证Token有效性

### 3. 文件验证
- **类型检查**: 仅允许jpg、jpeg、png、gif格式
- **大小限制**: 单文件最大10MB
- **数量限制**: 单次最多10个文件
- **Content-Type验证**: 检查MIME类型

### 4. CORS配置
```python
# 生产环境应限制允许的源
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://your-domain.com"],  # 替换为实际域名
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
```

### 5. SQL注入防护
- 使用参数化查询（已实现）
- 不拼接SQL字符串
- SQLite默认防护机制

### 6. 错误信息脱敏
- 生产环境不返回详细堆栈信息
- 敏感错误仅记录日志，不返回客户端

---

## 附录

### A. API完整示例

#### 获取Token
```bash
# 请求
GET https://c4.yonyoucloud.com/iuap-api-auth/open-auth/selfAppAuth/base/v1/getAccessToken?appKey=2b2c5f61d8734cd49e76f8f918977c5d&timestamp=1696300000000&signature=xxx

# 响应
{
    "code": "00000",
    "data": {
        "access_token": "eyJhbGciOiJIUzI1NiIs...",
        "expires_in": 3600
    }
}
```

#### 上传文件
```bash
# 请求
POST /api/upload
Content-Type: multipart/form-data

business_id=123456
files=@image1.jpg
files=@image2.jpg

# 响应
{
    "success": true,
    "total": 2,
    "succeeded": 2,
    "failed": 0,
    "results": [
        {
            "file_name": "image1.jpg",
            "success": true,
            "file_id": "6188e00d93db980027b8bff2",
            "file_size": 123456,
            "file_extension": ".jpg"
        },
        {
            "file_name": "image2.jpg",
            "success": true,
            "file_id": "6188e00d93db980027b8bff3",
            "file_size": 234567,
            "file_extension": ".jpg"
        }
    ]
}
```

#### 查询历史
```bash
# 请求
GET /api/history/123456

# 响应
{
    "business_id": "123456",
    "total_count": 15,
    "success_count": 14,
    "failed_count": 1,
    "records": [
        {
            "id": 1,
            "file_name": "image1.jpg",
            "file_size": 123456,
            "file_extension": ".jpg",
            "upload_time": "2025-10-03 10:30:00",
            "status": "success",
            "yonyou_file_id": "6188e00d93db980027b8bff2",
            "retry_count": 0
        }
    ]
}
```

### B. 错误码映射表

| 错误码 | 来源 | 含义 | 处理方式 |
|--------|------|------|---------|
| 1090003500065 | 用友云 | 未包含租户及用户信息 | 刷新Token并重试 |
| FILE_TOO_LARGE | 本地 | 文件大小超限 | 提示用户压缩图片 |
| FILE_COUNT_EXCEEDED | 本地 | 文件数量超限 | 提示用户减少图片 |
| INVALID_FILE_TYPE | 本地 | 文件格式不支持 | 提示支持的格式 |
| NETWORK_ERROR | 本地 | 网络请求失败 | 自动重试3次 |
| INVALID_BUSINESS_ID | 本地 | businessId格式错误 | 提示重新扫码 |

### C. 性能指标

| 指标 | 目标值 | 测量方法 |
|------|--------|---------|
| 页面加载时间 | <1秒 | Chrome DevTools |
| 单文件上传时间 | <5秒 | 网络监控 |
| 10文件批量上传 | <30秒 | 计时器 |
| Token获取时间 | <2秒 | 日志统计 |
| 数据库查询时间 | <100ms | SQL日志 |
| 并发处理能力 | 10用户同时上传 | 压力测试 |

### D. 日志规范

```python
# 推荐使用Python logging模块
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/app.log'),
        logging.StreamHandler()
    ]
)

# 关键日志点
# 1. Token获取
logger.info(f"Token获取成功, expires_in={expires_in}")

# 2. 文件上传
logger.info(f"开始上传文件: business_id={business_id}, file_name={file_name}")

# 3. 上传结果
logger.info(f"上传成功: file_id={file_id}")
logger.error(f"上传失败: error_code={error_code}, message={error_message}")

# 4. 重试
logger.warning(f"上传失败，正在重试 ({attempt}/{max_retry})")
```

---

**文档版本**: 1.0.0
**最后更新**: 2025-10-03
**状态**: 实现就绪 ✓

此技术规范已包含所有实现所需的细节，可直接进入编码阶段。
