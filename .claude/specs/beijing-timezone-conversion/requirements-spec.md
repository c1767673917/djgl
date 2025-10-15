# 北京时区转换技术规格文档

**版本**: v1.0
**生成时间**: 2025-10-15
**实施状态**: 就绪

---

## 问题陈述

### 业务问题
当前系统在时间处理上存在三层不一致：
1. **数据库层**：SQLite 使用 `CURRENT_TIMESTAMP` 默认值，返回 UTC 时间
2. **后端应用层**：Python 使用 `datetime.now()` 生成 naive datetime（系统本地时区）
3. **前端显示层**：JavaScript 使用浏览器本地时区格式化时间

这导致：
- 时间显示不一致（数据库 UTC vs 应用层本地时间）
- 用户无法直观理解记录时间
- 跨地域部署时会产生时间混乱

### 当前状态
**受影响的时间字段**：
- `upload_history.upload_time` - 上传时间（核心字段）
- `upload_history.created_at` - 记录创建时间
- `upload_history.updated_at` - 记录更新时间
- `upload_history.deleted_at` - 软删除时间

**问题位置统计**：
- 后端：3 个文件，4 个关键位置
- 前端：2 个文件，2 个显示位置
- 数据库：1 个表定义，4 个时间字段

### 预期结果
1. **功能正确性**：所有时间统一显示为北京时间（UTC+8）
2. **格式统一**：`2025-10-15 14:30:45` （无时区标识）
3. **无缝集成**：与现有异步架构和用友云 API 兼容
4. **数据清洁**：清除历史数据，从新时区开始

---

## 解决方案概览

### 核心策略
采用**应用层时区控制策略**，完全由 Python 后端生成北京时间，不依赖数据库默认值：

1. **集中管理**：创建统一的时区工具模块 `app/core/timezone.py`
2. **数据库存储**：直接存储 naive datetime（北京时间，无时区信息）
3. **API 响应**：返回 ISO 8601 格式字符串（`2025-10-15T14:30:45`）
4. **前端显示**：接收后端字符串，格式化为 `YYYY-MM-DD HH:MM:SS`

### 主要变更
1. ✅ 新建时区工具模块（`app/core/timezone.py`）
2. ✅ 移除数据库 `CURRENT_TIMESTAMP` 依赖
3. ✅ 替换所有 `datetime.now()` 调用
4. ✅ 清空历史数据（SQL 脚本）
5. ✅ 统一前端时间格式化

### 成功标准
- 所有新记录的时间字段显示北京时间
- 前端管理页面和上传页面时间一致
- 导出功能时间格式正确
- 删除功能的 `deleted_at` 字段使用北京时间

---

## 技术实施计划

### 实施阶段划分

#### 阶段 1：准备阶段（预计 10 分钟）
创建时区工具模块并验证功能。

#### 阶段 2：数据库清理（预计 2 分钟）
清空现有历史数据。

#### 阶段 3：后端改造（预计 15 分钟）
替换所有时间生成逻辑。

#### 阶段 4：前端改造（预计 10 分钟）
统一时间显示格式。

#### 阶段 5：验证测试（预计 15 分钟）
功能验证和回归测试。

---

## 详细代码改动清单

### 改动 1：创建时区工具模块

**文件路径**：`/Users/lichuansong/Desktop/projects/单据上传管理/app/core/timezone.py`

**操作类型**：新建文件

**完整代码**：
```python
"""
北京时区工具模块

提供统一的北京时间（UTC+8）生成函数。
"""
from datetime import datetime, timezone, timedelta


# 北京时区常量（UTC+8）
BEIJING_TZ = timezone(timedelta(hours=8))


def get_beijing_now() -> datetime:
    """
    获取当前北京时间（带时区信息）

    Returns:
        datetime: 带有 UTC+8 时区信息的 datetime 对象

    Example:
        >>> dt = get_beijing_now()
        >>> print(dt.tzinfo)  # UTC+08:00
    """
    return datetime.now(BEIJING_TZ)


def get_beijing_now_naive() -> datetime:
    """
    获取当前北京时间（无时区信息，用于数据库存储）

    Returns:
        datetime: 不带时区信息的 naive datetime 对象（北京时间）

    Example:
        >>> dt = get_beijing_now_naive()
        >>> print(dt.tzinfo)  # None
        >>> print(dt.strftime('%Y-%m-%d %H:%M:%S'))  # 2025-10-15 14:30:45
    """
    return datetime.now(BEIJING_TZ).replace(tzinfo=None)


def format_beijing_time(dt: datetime) -> str:
    """
    将 datetime 对象格式化为标准字符串（用于 API 响应）

    Args:
        dt: datetime 对象（可带时区或不带时区）

    Returns:
        str: ISO 8601 格式字符串（无时区标识），如 '2025-10-15T14:30:45'

    Example:
        >>> dt = get_beijing_now_naive()
        >>> format_beijing_time(dt)  # '2025-10-15T14:30:45'
    """
    if dt is None:
        return None

    # 如果是 aware datetime（带时区），先转换为北京时区
    if dt.tzinfo is not None:
        dt = dt.astimezone(BEIJING_TZ).replace(tzinfo=None)

    return dt.strftime('%Y-%m-%dT%H:%M:%S')
```

**说明**：
- `BEIJING_TZ`：全局时区常量，避免重复创建
- `get_beijing_now()`：获取带时区信息的北京时间（用于计算）
- `get_beijing_now_naive()`：**核心函数**，用于数据库插入和更新
- `format_beijing_time()`：用于 API 响应格式化（可选使用）

---

### 改动 2：修改 UploadHistory 模型

**文件路径**：`/Users/lichuansong/Desktop/projects/单据上传管理/app/models/upload_history.py`

**操作类型**：修改现有代码

**原始代码**（第 1-30 行）：
```python
from datetime import datetime
from typing import Optional


class UploadHistory:
    def __init__(
        self,
        id: Optional[int] = None,
        business_id: str = "",
        doc_number: Optional[str] = None,
        doc_type: Optional[str] = None,
        file_name: str = "",
        file_size: int = 0,
        file_extension: str = "",
        upload_time: Optional[datetime] = None,
        status: str = "pending",
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
        yonyou_file_id: Optional[str] = None,
        retry_count: int = 0,
        local_file_path: Optional[str] = None
    ):
        self.id = id
        self.business_id = business_id
        self.doc_number = doc_number
        self.doc_type = doc_type
        self.file_name = file_name
        self.file_size = file_size
        self.file_extension = file_extension
        self.upload_time = upload_time or datetime.now()  # ← 第 30 行，需要修改
        self.status = status
        self.error_code = error_code
        self.error_message = error_message
        self.yonyou_file_id = yonyou_file_id
        self.retry_count = retry_count
        self.local_file_path = local_file_path
```

**修改后代码**：
```python
from datetime import datetime
from typing import Optional
from app.core.timezone import get_beijing_now_naive  # ← 新增导入


class UploadHistory:
    def __init__(
        self,
        id: Optional[int] = None,
        business_id: str = "",
        doc_number: Optional[str] = None,
        doc_type: Optional[str] = None,
        file_name: str = "",
        file_size: int = 0,
        file_extension: str = "",
        upload_time: Optional[datetime] = None,
        status: str = "pending",
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
        yonyou_file_id: Optional[str] = None,
        retry_count: int = 0,
        local_file_path: Optional[str] = None
    ):
        self.id = id
        self.business_id = business_id
        self.doc_number = doc_number
        self.doc_type = doc_type
        self.file_name = file_name
        self.file_size = file_size
        self.file_extension = file_extension
        self.upload_time = upload_time or get_beijing_now_naive()  # ← 修改：使用北京时间
        self.status = status
        self.error_code = error_code
        self.error_message = error_message
        self.yonyou_file_id = yonyou_file_id
        self.retry_count = retry_count
        self.local_file_path = local_file_path
```

**变更说明**：
- **第 3 行**：新增 `from app.core.timezone import get_beijing_now_naive`
- **第 30 行**：将 `datetime.now()` 替换为 `get_beijing_now_naive()`

---

### 改动 3：修改 admin.py 导出时间戳

**文件路径**：`/Users/lichuansong/Desktop/projects/单据上传管理/app/api/admin.py`

**操作类型**：修改现有代码

**第一处：导入时区工具（文件头部）**

**原始代码**（第 1-14 行）：
```python
from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from typing import List, Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel
import csv
import io
import os
import zipfile
import tempfile
from pathlib import Path
from openpyxl import Workbook
from app.core.database import get_db_connection
from app.core.config import get_settings
```

**修改后代码**：
```python
from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from typing import List, Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel
import csv
import io
import os
import zipfile
import tempfile
from pathlib import Path
from openpyxl import Workbook
from app.core.database import get_db_connection
from app.core.config import get_settings
from app.core.timezone import get_beijing_now_naive  # ← 新增导入
```

**第二处：修改导出时间戳生成（第 174 行）**

**原始代码**（第 172-176 行）：
```python
    # 创建临时目录和ZIP文件
    temp_dir = tempfile.mkdtemp()
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')  # ← 第 174 行，需要修改
    zip_filename = f"upload_records_{timestamp}.zip"
    zip_path = os.path.join(temp_dir, zip_filename)
```

**修改后代码**：
```python
    # 创建临时目录和ZIP文件
    temp_dir = tempfile.mkdtemp()
    timestamp = get_beijing_now_naive().strftime('%Y%m%d_%H%M%S')  # ← 修改：使用北京时间
    zip_filename = f"upload_records_{timestamp}.zip"
    zip_path = os.path.join(temp_dir, zip_filename)
```

**第三处：修改软删除时间生成（第 323 行）**

**原始代码**（第 318-329 行）：
```python
    try:
        # 构建IN子句的占位符
        placeholders = ','.join('?' * len(request.ids))

        # 软删除：设置deleted_at字段为当前时间
        current_time = datetime.now().isoformat()  # ← 第 323 行，需要修改
        cursor.execute(f"""
            UPDATE upload_history
            SET deleted_at = ?
            WHERE id IN ({placeholders})
            AND deleted_at IS NULL
        """, [current_time] + request.ids)
```

**修改后代码**：
```python
    try:
        # 构建IN子句的占位符
        placeholders = ','.join('?' * len(request.ids))

        # 软删除：设置deleted_at字段为当前时间（北京时间）
        current_time = get_beijing_now_naive().isoformat()  # ← 修改：使用北京时间
        cursor.execute(f"""
            UPDATE upload_history
            SET deleted_at = ?
            WHERE id IN ({placeholders})
            AND deleted_at IS NULL
        """, [current_time] + request.ids)
```

**变更说明**：
- **导入语句**：新增时区工具导入
- **第 174 行**：导出文件名时间戳改用北京时间
- **第 323 行**：软删除时间改用北京时间

---

### 改动 4：修改数据库初始化脚本

**文件路径**：`/Users/lichuansong/Desktop/projects/单据上传管理/app/core/database.py`

**操作类型**：修改现有代码

**原始代码**（第 17-42 行）：
```python
def init_database():
    """初始化数据库"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # 创建上传历史表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS upload_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id VARCHAR(50) NOT NULL,
            doc_number VARCHAR(100),
            doc_type VARCHAR(20),
            file_name VARCHAR(255) NOT NULL,
            file_size INTEGER NOT NULL,
            file_extension VARCHAR(20),
            upload_time DATETIME DEFAULT CURRENT_TIMESTAMP,  -- ← 需要移除默认值
            status VARCHAR(20) NOT NULL,
            error_code VARCHAR(50),
            error_message TEXT,
            yonyou_file_id VARCHAR(255),
            retry_count INTEGER DEFAULT 0,
            local_file_path VARCHAR(500),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,  -- ← 需要移除默认值
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP   -- ← 需要移除默认值
        )
    """)
```

**修改后代码**：
```python
def init_database():
    """初始化数据库"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # 创建上传历史表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS upload_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id VARCHAR(50) NOT NULL,
            doc_number VARCHAR(100),
            doc_type VARCHAR(20),
            file_name VARCHAR(255) NOT NULL,
            file_size INTEGER NOT NULL,
            file_extension VARCHAR(20),
            upload_time DATETIME,  -- ← 移除 DEFAULT CURRENT_TIMESTAMP，由应用层控制
            status VARCHAR(20) NOT NULL,
            error_code VARCHAR(50),
            error_message TEXT,
            yonyou_file_id VARCHAR(255),
            retry_count INTEGER DEFAULT 0,
            local_file_path VARCHAR(500),
            created_at DATETIME,  -- ← 移除 DEFAULT CURRENT_TIMESTAMP
            updated_at DATETIME   -- ← 移除 DEFAULT CURRENT_TIMESTAMP
        )
    """)
```

**变更说明**：
- **upload_time**：移除 `DEFAULT CURRENT_TIMESTAMP`
- **created_at**：移除 `DEFAULT CURRENT_TIMESTAMP`
- **updated_at**：移除 `DEFAULT CURRENT_TIMESTAMP`
- 这些字段的值将由应用层在插入记录时提供（北京时间）

**重要提示**：此改动仅影响**新建表**的场景。对于已存在的表，需要执行数据库清理脚本（见下文）。

---

### 改动 5：修改前端管理页面时间显示

**文件路径**：`/Users/lichuansong/Desktop/projects/单据上传管理/app/static/js/admin.js`

**操作类型**：修改现有代码

**原始代码**（第 262-273 行）：
```javascript
// 格式化日期时间
function formatDateTime(dateTimeStr) {
    if (!dateTimeStr) return '-';
    const date = new Date(dateTimeStr);
    return date.toLocaleString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
    });
}
```

**修改后代码**：
```javascript
// 格式化日期时间（标准化为 YYYY-MM-DD HH:MM:SS 格式）
function formatDateTime(dateTimeStr) {
    if (!dateTimeStr) return '-';

    // 后端返回 ISO 8601 格式（如 '2025-10-15T14:30:45'）或标准格式
    // 统一格式化为 'YYYY-MM-DD HH:MM:SS'
    try {
        const date = new Date(dateTimeStr);

        // 检查日期有效性
        if (isNaN(date.getTime())) {
            return dateTimeStr;  // 无效日期直接返回原字符串
        }

        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        const hours = String(date.getHours()).padStart(2, '0');
        const minutes = String(date.getMinutes()).padStart(2, '0');
        const seconds = String(date.getSeconds()).padStart(2, '0');

        return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
    } catch (e) {
        console.error('时间格式化失败:', dateTimeStr, e);
        return dateTimeStr;
    }
}
```

**变更说明**：
- **格式统一**：从浏览器本地化格式改为固定的 `YYYY-MM-DD HH:MM:SS`
- **容错处理**：增加日期有效性检查和异常捕获
- **说明注释**：明确后端数据格式和转换逻辑

**使用位置**：
- 第 160 行：`<td>${formatDateTime(record.upload_time)}</td>`

---

### 改动 6：修改前端上传页面时间显示

**文件路径**：`/Users/lichuansong/Desktop/projects/单据上传管理/app/static/js/app.js`

**操作类型**：修改现有代码

**原始代码**（第 360-363 行）：
```javascript
                    <div class="meta">
                        <div>大小: ${formatFileSize(record.file_size)}</div>
                        <div>时间: ${record.upload_time}</div>  // ← 第 362 行，直接显示
                        ${record.error_message ? `<div style="color: #ff4d4f;">错误: ${record.error_message}</div>` : ''}
                    </div>
```

**修改后代码**：
```javascript
                    <div class="meta">
                        <div>大小: ${formatFileSize(record.file_size)}</div>
                        <div>时间: ${formatDateTime(record.upload_time)}</div>  // ← 修改：使用格式化函数
                        ${record.error_message ? `<div style="color: #ff4d4f;">错误: ${record.error_message}</div>` : ''}
                    </div>
```

**新增格式化函数**（在 `formatFileSize` 函数后添加，第 393 行之后）：

```javascript
// 格式化文件大小
function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1024 / 1024).toFixed(1) + ' MB';
}

// 格式化日期时间（标准化为 YYYY-MM-DD HH:MM:SS 格式）
function formatDateTime(dateTimeStr) {
    if (!dateTimeStr) return '-';

    try {
        const date = new Date(dateTimeStr);

        // 检查日期有效性
        if (isNaN(date.getTime())) {
            return dateTimeStr;
        }

        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        const hours = String(date.getHours()).padStart(2, '0');
        const minutes = String(date.getMinutes()).padStart(2, '0');
        const seconds = String(date.getSeconds()).padStart(2, '0');

        return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
    } catch (e) {
        console.error('时间格式化失败:', dateTimeStr, e);
        return dateTimeStr;
    }
}
```

**变更说明**：
- **第 362 行**：调用 `formatDateTime()` 格式化时间
- **新增函数**：`formatDateTime()` 与管理页面保持一致

---

## 数据库操作脚本

### 脚本 1：清空历史数据

**文件路径**：手动执行或创建迁移脚本

**SQL 命令**：
```sql
-- 清空上传历史表所有数据
DELETE FROM upload_history;

-- 重置自增主键计数器
DELETE FROM sqlite_sequence WHERE name='upload_history';

-- 验证数据已清空
SELECT COUNT(*) as remaining_records FROM upload_history;
-- 预期结果：remaining_records = 0
```

**执行方式**：

**方式 1：使用 SQLite CLI**
```bash
# 进入项目目录
cd /Users/lichuansong/Desktop/projects/单据上传管理

# 打开数据库
sqlite3 ./data/upload_manager.db

# 执行删除命令
DELETE FROM upload_history;
DELETE FROM sqlite_sequence WHERE name='upload_history';

# 验证
SELECT COUNT(*) FROM upload_history;

# 退出
.exit
```

**方式 2：使用 Python 脚本**

创建文件：`/Users/lichuansong/Desktop/projects/单据上传管理/scripts/clear_history_data.py`

```python
"""
清空历史数据脚本

警告：此操作不可逆，执行前请确认已备份重要数据！
"""
import sqlite3
import sys
from pathlib import Path

# 添加项目路径到 sys.path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.database import get_db_connection


def clear_history_data():
    """清空上传历史数据"""

    # 二次确认
    print("⚠️  警告：此操作将清空所有上传历史记录！")
    print("⚠️  请确认您已备份重要数据。")
    confirm = input("确认清空？(yes/no): ").strip().lower()

    if confirm != 'yes':
        print("❌ 操作已取消。")
        return

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # 查询当前记录数
        cursor.execute("SELECT COUNT(*) FROM upload_history")
        count_before = cursor.fetchone()[0]
        print(f"\n📊 当前记录数: {count_before}")

        if count_before == 0:
            print("✅ 数据库已经是空的，无需清理。")
            conn.close()
            return

        # 执行清空操作
        print("\n🗑️  正在清空数据...")
        cursor.execute("DELETE FROM upload_history")
        cursor.execute("DELETE FROM sqlite_sequence WHERE name='upload_history'")
        conn.commit()

        # 验证清空结果
        cursor.execute("SELECT COUNT(*) FROM upload_history")
        count_after = cursor.fetchone()[0]

        if count_after == 0:
            print(f"✅ 成功清空 {count_before} 条记录！")
            print("✅ 主键计数器已重置。")
        else:
            print(f"⚠️  警告：仍有 {count_after} 条记录未删除。")

        conn.close()

    except Exception as e:
        print(f"❌ 清空失败: {str(e)}")
        raise


if __name__ == "__main__":
    clear_history_data()
```

**执行命令**：
```bash
cd /Users/lichuansong/Desktop/projects/单据上传管理
python scripts/clear_history_data.py
```

**注意事项**：
- ⚠️ **不可逆操作**：删除后无法恢复
- 建议先备份数据库文件：`cp ./data/upload_manager.db ./data/upload_manager.db.backup`
- 清空后，新记录将从 `id=1` 开始

---

### 脚本 2：数据库表结构更新（可选）

**说明**：如果数据库表已存在且使用了 `CURRENT_TIMESTAMP` 默认值，可执行以下迁移脚本。

**注意**：SQLite 不支持直接 `ALTER COLUMN`，需要重建表。

**迁移脚本**：

创建文件：`/Users/lichuansong/Desktop/projects/单据上传管理/scripts/migrate_table_schema.py`

```python
"""
数据库表结构迁移脚本

移除 upload_time, created_at, updated_at 的 DEFAULT CURRENT_TIMESTAMP
"""
import sqlite3
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.database import get_db_connection


def migrate_schema():
    """迁移表结构"""

    print("📋 开始迁移数据库表结构...")

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # 1. 创建新表（无 DEFAULT CURRENT_TIMESTAMP）
        print("1️⃣  创建新表结构...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS upload_history_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                business_id VARCHAR(50) NOT NULL,
                doc_number VARCHAR(100),
                doc_type VARCHAR(20),
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
                deleted_at TEXT DEFAULT NULL
            )
        """)

        # 2. 复制数据（如果需要保留旧数据）
        # 由于已清空数据，此步骤可跳过
        # cursor.execute("""
        #     INSERT INTO upload_history_new
        #     SELECT * FROM upload_history
        # """)

        # 3. 删除旧表
        print("2️⃣  删除旧表...")
        cursor.execute("DROP TABLE IF EXISTS upload_history")

        # 4. 重命名新表
        print("3️⃣  重命名新表...")
        cursor.execute("ALTER TABLE upload_history_new RENAME TO upload_history")

        # 5. 重建索引
        print("4️⃣  重建索引...")
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
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_doc_number
            ON upload_history(doc_number)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_doc_type
            ON upload_history(doc_type)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_deleted_at
            ON upload_history(deleted_at)
        """)

        conn.commit()
        print("✅ 表结构迁移完成！")

        conn.close()

    except Exception as e:
        print(f"❌ 迁移失败: {str(e)}")
        raise


if __name__ == "__main__":
    migrate_schema()
```

**执行顺序**：
1. 先执行 `clear_history_data.py` 清空数据
2. 再执行 `migrate_table_schema.py` 更新表结构

---

## 实施顺序

### 第一阶段：准备工作（预计 10 分钟）

1. **创建时区工具模块**
   - 创建文件：`app/core/timezone.py`
   - 验证导入：`python -c "from app.core.timezone import get_beijing_now_naive; print(get_beijing_now_naive())"`

2. **创建清理脚本**
   - 创建目录：`mkdir -p scripts`
   - 创建文件：`scripts/clear_history_data.py`
   - 创建文件：`scripts/migrate_table_schema.py`（可选）

### 第二阶段：数据库清理（预计 2 分钟）

1. **备份现有数据库**
   ```bash
   cp ./data/upload_manager.db ./data/upload_manager.db.backup_$(date +%Y%m%d_%H%M%S)
   ```

2. **执行数据清空**
   ```bash
   python scripts/clear_history_data.py
   ```

3. **执行表结构迁移（可选）**
   ```bash
   python scripts/migrate_table_schema.py
   ```

### 第三阶段：后端改造（预计 15 分钟）

按以下顺序修改文件：

1. **修改 `app/models/upload_history.py`**
   - 导入 `get_beijing_now_naive`
   - 替换第 30 行的 `datetime.now()`

2. **修改 `app/api/admin.py`**
   - 导入 `get_beijing_now_naive`
   - 替换第 174 行（导出时间戳）
   - 替换第 323 行（软删除时间）

3. **修改 `app/core/database.py`**
   - 移除 `upload_time`, `created_at`, `updated_at` 的 `DEFAULT CURRENT_TIMESTAMP`

### 第四阶段：前端改造（预计 10 分钟）

1. **修改 `app/static/js/admin.js`**
   - 替换 `formatDateTime` 函数（第 262-273 行）

2. **修改 `app/static/js/app.js`**
   - 新增 `formatDateTime` 函数（第 393 行后）
   - 修改第 362 行，使用 `formatDateTime()`

### 第五阶段：验证测试（预计 15 分钟）

见下文"验证计划"部分。

---

## 验证计划

### 验证检查清单

#### 1. 后端时间生成验证

**测试脚本**：
```python
# 测试时区工具函数
from app.core.timezone import get_beijing_now_naive, get_beijing_now, format_beijing_time
from datetime import datetime

# 1. 测试 get_beijing_now_naive()
dt_naive = get_beijing_now_naive()
print(f"北京时间（naive）: {dt_naive}")
print(f"是否带时区: {dt_naive.tzinfo}")  # 应为 None

# 2. 测试 get_beijing_now()
dt_aware = get_beijing_now()
print(f"北京时间（aware）: {dt_aware}")
print(f"时区信息: {dt_aware.tzinfo}")  # 应为 UTC+08:00

# 3. 测试 format_beijing_time()
formatted = format_beijing_time(dt_naive)
print(f"格式化结果: {formatted}")  # 应为 2025-10-15T14:30:45

# 4. 验证与系统时间的差异（如果系统是 UTC+8 应该一致）
system_time = datetime.now()
print(f"系统时间: {system_time}")
print(f"时间差: {abs((dt_naive - system_time).total_seconds())} 秒")
```

**预期结果**：
- `dt_naive.tzinfo` 为 `None`
- `dt_aware.tzinfo` 显示 `UTC+08:00`
- 格式化结果符合 ISO 8601 格式
- 与北京时间一致

---

#### 2. 数据库插入验证

**测试步骤**：

1. **上传测试图片**
   - 访问：`http://localhost:8000/?business_id=123456&doc_number=TEST001&doc_type=销售`
   - 上传一张测试图片
   - 观察上传时间

2. **查询数据库**
   ```bash
   sqlite3 ./data/upload_manager.db
   SELECT upload_time, created_at, updated_at FROM upload_history ORDER BY id DESC LIMIT 1;
   .exit
   ```

3. **验证 API 响应**
   ```bash
   curl -s "http://localhost:8000/api/history/123456" | jq '.records[0].upload_time'
   ```

**预期结果**：
- 数据库中的时间为北京时间（与当前北京时间一致）
- API 返回的时间格式为 `2025-10-15T14:30:45`

---

#### 3. 前端显示验证

**测试步骤**：

1. **管理页面验证**
   - 访问：`http://localhost:8000/admin`
   - 检查"上传时间"列的格式
   - 确认格式为 `2025-10-15 14:30:45`

2. **上传页面历史记录验证**
   - 访问：`http://localhost:8000/?business_id=123456&doc_number=TEST001&doc_type=销售`
   - 点击"查看历史"
   - 检查时间显示格式

**预期结果**：
- 所有时间显示格式统一为 `YYYY-MM-DD HH:MM:SS`
- 时间与北京时间一致
- 无浏览器时区转换（直接显示后端返回值）

---

#### 4. 导出功能验证

**测试步骤**：

1. **导出记录**
   - 在管理页面点击"导出记录"
   - 下载 ZIP 文件
   - 解压并打开 Excel 文件

2. **检查文件名时间戳**
   - 文件名格式：`upload_records_20251015_143045.zip`
   - 验证时间戳为北京时间

3. **检查 Excel 中的时间列**
   - "上传时间"列的值应为北京时间
   - 格式应为数据库原始格式（由 Excel 自动识别）

**预期结果**：
- ZIP 文件名时间戳为北京时间
- Excel 中时间数据正确

---

#### 5. 删除功能验证

**测试步骤**：

1. **执行软删除**
   - 在管理页面选中一条记录
   - 点击"删除"
   - 确认删除

2. **查询数据库验证**
   ```bash
   sqlite3 ./data/upload_manager.db
   SELECT deleted_at FROM upload_history WHERE deleted_at IS NOT NULL LIMIT 1;
   .exit
   ```

**预期结果**：
- `deleted_at` 字段的值为北京时间
- 格式为 ISO 8601：`2025-10-15T14:30:45`

---

#### 6. 回归测试

**测试场景**：

1. **批量上传**：一次上传 10 张图片，验证所有记录时间正确
2. **重试机制**：模拟上传失败，验证重试后的时间记录
3. **分页查询**：在管理页面翻页，验证所有记录时间格式一致
4. **筛选功能**：按日期范围筛选，验证时间筛选逻辑正确

**预期结果**：
- 所有功能正常工作
- 时间显示一致且正确

---

## 回滚方案

如果实施后出现问题，可按以下步骤回滚：

### 步骤 1：恢复代码

```bash
# 回退所有代码改动
git checkout HEAD app/models/upload_history.py
git checkout HEAD app/api/admin.py
git checkout HEAD app/core/database.py
git checkout HEAD app/static/js/admin.js
git checkout HEAD app/static/js/app.js

# 删除新建的时区工具模块
rm app/core/timezone.py
```

### 步骤 2：恢复数据库

```bash
# 恢复数据库备份
cp ./data/upload_manager.db.backup ./data/upload_manager.db
```

### 步骤 3：重启服务

```bash
# 重启 FastAPI 应用
# 如果使用 systemd
sudo systemctl restart upload-manager

# 或者手动重启
pkill -f "uvicorn"
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 步骤 4：验证回滚

- 访问管理页面，确认系统恢复正常
- 测试上传功能

---

## 技术决策记录

### 决策 1：数据库直接存储北京时间（naive datetime）

**原因**：
- ✅ 简化实现：无需在查询时转换时区
- ✅ 与 SQLite 最佳实践一致（SQLite 对时区支持有限）
- ✅ 减少前后端转换复杂度
- ❌ 缺点：不支持多时区场景

**替代方案**：存储 UTC + 应用层转换
- 优点：符合国际化最佳实践
- 缺点：增加实现复杂度，当前业务不需要

### 决策 2：API 返回 ISO 8601 格式（无时区标识）

**原因**：
- ✅ 标准化格式，前端易于解析
- ✅ 避免时区混淆（明确为北京时间）
- ✅ 与数据库存储格式一致

**格式示例**：`2025-10-15T14:30:45`

### 决策 3：前端固定格式显示（不使用 `toLocaleString`）

**原因**：
- ✅ 跨浏览器一致性
- ✅ 避免用户时区影响
- ✅ 符合业务需求（仅显示北京时间）

**格式示例**：`2025-10-15 14:30:45`

### 决策 4：清空历史数据而非迁移

**原因**：
- ✅ 用户已确认可接受
- ✅ 避免时区转换错误
- ✅ 简化实施流程
- ❌ 缺点：丢失历史数据

---

## 边界情况处理

### 1. 用友云 API 返回的时间

**策略**：不做处理，保持原样

**原因**：
- 用友云 API 返回的时间仅用于 token 过期判断
- 不涉及展示或业务逻辑
- 修改可能引入兼容性问题

### 2. 历史数据已清除

**影响**：
- 所有历史上传记录将被删除
- 新记录 ID 从 1 开始

**风险缓解**：
- 实施前已通过需求确认文档与用户确认
- 提供数据库备份机制

### 3. 跨时区访问

**当前范围**：仅支持北京时间

**未来扩展**：
- 如需支持多时区，需重构为 timezone-aware 架构
- 数据库存储改为 UTC
- API 响应包含时区信息（ISO 8601 完整格式）
- 前端根据用户时区转换

### 4. 系统时钟不准确

**风险**：
- 如果服务器系统时间不准确，生成的北京时间也会不准确

**建议**：
- 配置 NTP 时间同步
- 定期检查服务器时间

---

## 依赖项说明

### Python 标准库依赖

本实施方案**无需安装额外依赖**，仅使用 Python 标准库：

```python
from datetime import datetime, timezone, timedelta
```

这些模块在 Python 3.6+ 中均已内置。

### 项目现有依赖

确认以下依赖已安装（项目已有）：

- `fastapi`
- `sqlite3`（Python 内置）
- `pydantic`

---

## 性能影响评估

### 影响分析

1. **时间生成性能**
   - `get_beijing_now_naive()` 执行时间：< 0.001ms
   - 相比 `datetime.now()` 增加一次时区转换，性能影响可忽略

2. **数据库性能**
   - 移除 `DEFAULT CURRENT_TIMESTAMP` 后，插入操作由应用层提供值
   - 性能无明显差异（数据库仍需写入相同数据）

3. **前端性能**
   - 新的 `formatDateTime` 函数使用原生 JS，性能优于 `toLocaleString`
   - 批量格式化 1000 条记录：< 10ms

**结论**：性能影响可忽略不计。

---

## 安全性考虑

### 时间注入攻击

**风险**：无

**原因**：
- 时间值由应用层生成，不接受用户输入
- 数据库插入使用参数化查询（`?` 占位符）

### 时间戳伪造

**风险**：低

**原因**：
- `upload_time` 在对象初始化时生成，无外部接口修改
- 用户无法通过 API 修改时间戳

---

## 文档更新清单

实施完成后，需要更新以下文档（如果存在）：

1. **API 文档**
   - 更新时间字段格式说明（ISO 8601）
   - 明确所有时间均为北京时间

2. **开发文档**
   - 新增时区工具模块使用说明
   - 更新时间处理最佳实践

3. **数据库设计文档**
   - 更新表结构定义（移除 DEFAULT CURRENT_TIMESTAMP）
   - 说明时间字段由应用层控制

---

## 附录

### 附录 A：完整文件修改清单

| 文件路径 | 操作类型 | 改动行号 | 说明 |
|---------|---------|----------|------|
| `app/core/timezone.py` | 新建 | - | 时区工具模块 |
| `app/models/upload_history.py` | 修改 | 3, 30 | 导入并使用北京时间 |
| `app/api/admin.py` | 修改 | 15, 174, 323 | 导入并使用北京时间 |
| `app/core/database.py` | 修改 | 32, 39, 40 | 移除时间字段默认值 |
| `app/static/js/admin.js` | 修改 | 262-273 | 替换时间格式化函数 |
| `app/static/js/app.js` | 修改 | 362, 393+ | 使用时间格式化函数 |
| `scripts/clear_history_data.py` | 新建 | - | 数据清理脚本 |
| `scripts/migrate_table_schema.py` | 新建 | - | 表结构迁移脚本 |

---

### 附录 B：时间格式对照表

| 场景 | 格式 | 示例 | 说明 |
|------|------|------|------|
| 数据库存储 | `YYYY-MM-DD HH:MM:SS` | `2025-10-15 14:30:45` | naive datetime 转字符串 |
| API 响应 | `YYYY-MM-DDTHH:MM:SS` | `2025-10-15T14:30:45` | ISO 8601（无时区） |
| 前端显示 | `YYYY-MM-DD HH:MM:SS` | `2025-10-15 14:30:45` | 用户可读格式 |
| 导出文件名 | `YYYYMMDD_HHMMSS` | `20251015_143045` | 无分隔符格式 |

---

### 附录 C：常见问题 FAQ

**Q1: 为什么不使用 UTC 存储？**

A: 当前业务仅在中国区域使用，不涉及多时区场景。直接存储北京时间可简化实现并降低复杂度。如未来需要国际化，可迁移到 UTC 存储方案。

---

**Q2: 如果服务器部署在非 UTC+8 时区会怎样？**

A: `get_beijing_now_naive()` 使用绝对时区偏移（`timedelta(hours=8)`），不依赖服务器系统时区，因此在任何时区的服务器上都能正确生成北京时间。

---

**Q3: 数据库已有数据怎么办？**

A: 需求已确认直接清除历史数据。执行 `scripts/clear_history_data.py` 即可。

---

**Q4: 前端用户在不同时区访问会有问题吗？**

A: 不会。前端直接显示后端返回的北京时间字符串，不进行时区转换。所有用户看到的都是北京时间。

---

**Q5: 如何验证时间是否正确？**

A: 对比当前北京时间（可访问 `https://time.is/Beijing`）与系统显示的时间，应完全一致。

---

### 附录 D：测试用例

#### 用例 1：上传功能时间验证

**前置条件**：系统已完成改造

**步骤**：
1. 访问 `http://localhost:8000/?business_id=999999&doc_number=TEST-TIME-001&doc_type=销售`
2. 上传一张测试图片
3. 记录上传时的实际北京时间（如 14:30:45）
4. 查看管理页面的上传时间

**预期结果**：
- 管理页面显示时间与实际上传时间一致
- 格式为 `2025-10-15 14:30:45`

---

#### 用例 2：删除功能时间验证

**步骤**：
1. 在管理页面删除一条记录
2. 记录删除时的实际北京时间
3. 查询数据库：
   ```sql
   SELECT deleted_at FROM upload_history WHERE deleted_at IS NOT NULL ORDER BY id DESC LIMIT 1;
   ```

**预期结果**：
- `deleted_at` 字段值与实际删除时间一致

---

#### 用例 3：导出功能时间验证

**步骤**：
1. 记录导出时的实际北京时间（如 14:30:45）
2. 点击"导出记录"
3. 检查下载的 ZIP 文件名

**预期结果**：
- 文件名包含正确的时间戳，如 `upload_records_20251015_143045.zip`

---

### 附录 E：代码审查检查表

实施完成后，进行以下检查：

- [ ] `app/core/timezone.py` 文件创建且函数测试通过
- [ ] `app/models/upload_history.py` 已导入 `get_beijing_now_naive`
- [ ] `app/api/admin.py` 三处 `datetime.now()` 已全部替换
- [ ] `app/core/database.py` 移除了 `DEFAULT CURRENT_TIMESTAMP`
- [ ] `app/static/js/admin.js` 的 `formatDateTime` 函数已更新
- [ ] `app/static/js/app.js` 新增了 `formatDateTime` 函数并使用
- [ ] 历史数据已清空
- [ ] 所有改动已提交到版本控制系统
- [ ] 至少完成 3 个核心功能的验证测试

---

## 实施完成确认

实施完成后，请确认以下所有检查项：

### 功能验证
- [ ] 上传功能正常，时间显示为北京时间
- [ ] 管理页面时间格式统一为 `YYYY-MM-DD HH:MM:SS`
- [ ] 历史记录查看时间正确
- [ ] 导出功能时间戳正确
- [ ] 删除功能 `deleted_at` 字段正确

### 代码质量
- [ ] 所有修改已通过代码审查
- [ ] 无语法错误和导入错误
- [ ] 遵循项目现有代码风格
- [ ] 关键函数已添加文档注释

### 文档完整性
- [ ] 技术规格文档已保存
- [ ] 变更日志已记录
- [ ] 回滚方案已验证可行

---

**文档结束**

本技术规格文档已就绪，可直接用于代码生成和实施。
