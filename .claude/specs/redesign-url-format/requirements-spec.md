# 技术规格文档：URL格式重构与管理页面新增

**项目**: 单据上传管理系统
**规格版本**: 1.0
**生成日期**: 2025-10-03
**实现优先级**: P0 (核心功能)

---

## 1. 问题陈述

### 1.1 业务问题
当前系统使用单一参数URL格式 `/{business_id}`，无法携带单据的业务属性信息（单据编号、单据类型），导致：
- 上传记录缺少业务语义，只能通过用友云ID追溯
- 无法按单据类型进行分类管理和统计
- 历史记录查询仅支持用友云business_id，不支持业务编号搜索
- 缺少直观的管理界面查看所有上传记录

### 1.2 当前状态
- **URL格式**: `http://192.168.1.4:10000/{business_id}`
- **存储字段**: 仅存储business_id、文件名、大小、上传时间
- **查询能力**: 仅支持通过business_id查询单个单据历史
- **管理方式**: 无可视化管理页面，需直接查询数据库

### 1.3 预期结果
- **新URL格式**: `http://192.168.1.4:10000/?business_id={id}&doc_number={编号}&doc_type={类型}`
- **完整记录**: 存储业务单据编号、类型等业务属性
- **管理页面**: 提供搜索、筛选、分页、导出功能的可视化管理界面
- **多维查询**: 支持按单据编号、类型、时间范围等多维度查询

---

## 2. 解决方案概述

### 2.1 解决策略
采用**查询参数替代路径参数**的URL设计，保持与用友云API的business_id兼容性，同时扩展业务属性参数。新增独立的管理后台页面，提供数据展示和导出功能。

### 2.2 核心变更
1. **URL格式变更**: 从路径参数 `/{business_id}` 改为查询参数 `/?business_id=x&doc_number=x&doc_type=x`
2. **数据库扩展**: 在upload_history表新增doc_number、doc_type字段
3. **前端改造**: 修改URL解析逻辑，支持查询参数提取
4. **新增管理页面**: 创建独立的/admin路由，提供表格管理界面
5. **新增管理API**: 实现分页、搜索、筛选、导出接口

### 2.3 成功标准
- [ ] 旧URL格式 `/{business_id}` 完全废弃，新格式正常工作
- [ ] 上传时自动保存doc_number和doc_type到数据库
- [ ] 管理页面可正常展示所有上传记录，支持搜索和筛选
- [ ] 导出功能可生成CSV格式的记录列表
- [ ] 二维码验证逻辑适配新URL格式
- [ ] 所有单元测试和集成测试通过

---

## 3. 技术实现

### 3.1 数据库变更

#### 3.1.1 表结构修改

**修改文件**: `/Users/lichuansong/Desktop/projects/单据上传管理/app/core/database.py`

**变更说明**: 在upload_history表中新增业务字段

**SQL迁移脚本**:
```sql
-- 检查字段是否已存在，若不存在则新增
ALTER TABLE upload_history ADD COLUMN doc_number VARCHAR(100);
ALTER TABLE upload_history ADD COLUMN doc_type VARCHAR(20);

-- 创建索引优化查询性能
CREATE INDEX IF NOT EXISTS idx_doc_number ON upload_history(doc_number);
CREATE INDEX IF NOT EXISTS idx_doc_type ON upload_history(doc_type);
CREATE INDEX IF NOT EXISTS idx_doc_type_upload_time ON upload_history(doc_type, upload_time);
```

**完整表结构**:
```sql
CREATE TABLE IF NOT EXISTS upload_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_id VARCHAR(50) NOT NULL,        -- 用友云业务ID
    doc_number VARCHAR(100),                 -- 单据编号（如SO20250103001）
    doc_type VARCHAR(20),                    -- 单据类型（销售/转库/其他）
    file_name VARCHAR(255) NOT NULL,         -- 文件名
    file_size INTEGER NOT NULL,              -- 文件大小（字节）
    file_extension VARCHAR(20),              -- 文件扩展名
    upload_time DATETIME DEFAULT CURRENT_TIMESTAMP,  -- 上传时间
    status VARCHAR(20) NOT NULL,             -- 状态（success/failed）
    error_code VARCHAR(50),                  -- 错误码
    error_message TEXT,                      -- 错误信息
    yonyou_file_id VARCHAR(255),             -- 用友云文件ID
    retry_count INTEGER DEFAULT 0,           -- 重试次数
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

#### 3.1.2 数据迁移策略

**处理现有数据**:
```sql
-- 现有记录的doc_number和doc_type为NULL
-- 不需要回填历史数据，新记录从重构后开始填充
```

**实现位置**: `app/core/database.py` 的 `init_database()` 函数

**实现逻辑**:
```python
def init_database():
    """初始化数据库"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # 创建表（包含新字段）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS upload_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id VARCHAR(50) NOT NULL,
            doc_number VARCHAR(100),
            doc_type VARCHAR(20),
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

    # 检查并新增字段（兼容现有数据库）
    cursor.execute("PRAGMA table_info(upload_history)")
    columns = [column[1] for column in cursor.fetchall()]

    if 'doc_number' not in columns:
        cursor.execute("ALTER TABLE upload_history ADD COLUMN doc_number VARCHAR(100)")

    if 'doc_type' not in columns:
        cursor.execute("ALTER TABLE upload_history ADD COLUMN doc_type VARCHAR(20)")

    # 创建索引
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_business_id ON upload_history(business_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_upload_time ON upload_history(upload_time)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_status ON upload_history(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_doc_number ON upload_history(doc_number)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_doc_type ON upload_history(doc_type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_doc_type_upload_time ON upload_history(doc_type, upload_time)")

    conn.commit()
    conn.close()
```

---

### 3.2 后端API改造

#### 3.2.1 路由定义变更

**修改文件**: `/Users/lichuansong/Desktop/projects/单据上传管理/app/main.py`

**变更前**:
```python
# 行号 40-42
@app.get("/{business_id}")
async def upload_page(business_id: str):
    return FileResponse("app/static/index.html")
```

**变更后**:
```python
# 使用根路由，支持查询参数
@app.get("/")
async def upload_page(
    business_id: str = Query(..., description="业务单据ID"),
    doc_number: str = Query(..., description="单据编号"),
    doc_type: str = Query(..., description="单据类型")
):
    """
    上传页面入口

    URL示例: /?business_id=2372677039643688969&doc_number=SO20250103001&doc_type=销售

    参数:
    - business_id: 用友云业务单据ID（纯数字）
    - doc_number: 业务单据编号（如SO20250103001）
    - doc_type: 单据类型（销售/转库/其他）
    """
    # 验证business_id格式
    if not business_id or not business_id.isdigit():
        raise HTTPException(status_code=400, detail="business_id必须为纯数字")

    # 验证doc_type枚举值
    valid_doc_types = ["销售", "转库", "其他"]
    if doc_type not in valid_doc_types:
        raise HTTPException(
            status_code=400,
            detail=f"doc_type必须为以下值之一: {', '.join(valid_doc_types)}"
        )

    return FileResponse("app/static/index.html")
```

**导入依赖**:
```python
from fastapi import Query, HTTPException
```

#### 3.2.2 上传API改造

**修改文件**: `/Users/lichuansong/Desktop/projects/单据上传管理/app/api/upload.py`

**变更位置**: `upload_files()` 函数参数和逻辑

**变更前**:
```python
# 行号 16-18
@router.post("/upload")
async def upload_files(
    business_id: str = Form(...),
    files: List[UploadFile] = File(...)
):
```

**变更后**:
```python
@router.post("/upload")
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

    响应格式:
    {
        "success": true,
        "total": 10,
        "succeeded": 9,
        "failed": 1,
        "results": [...]
    }
    """
    # 验证businessId格式
    if not business_id or not business_id.isdigit():
        raise HTTPException(status_code=400, detail="businessId必须为纯数字")

    # 验证doc_type枚举值
    valid_doc_types = ["销售", "转库", "其他"]
    if doc_type not in valid_doc_types:
        raise HTTPException(
            status_code=400,
            detail=f"doc_type必须为以下值之一: {', '.join(valid_doc_types)}"
        )

    # 验证doc_number格式（可选：根据业务规则添加）
    if not doc_number or len(doc_number.strip()) == 0:
        raise HTTPException(status_code=400, detail="doc_number不能为空")

    # ... 文件验证逻辑保持不变 ...
```

**修改历史记录保存逻辑**:

在 `upload_single_file()` 函数中，传递新参数：

```python
# 修改位置：行号 73-79
history = UploadHistory(
    business_id=business_id,
    doc_number=doc_number,      # 新增
    doc_type=doc_type,          # 新增
    file_name=upload_file.filename,
    file_size=file_size,
    file_extension="." + upload_file.filename.split(".")[-1].lower(),
    status="pending"
)
```

**修改数据库保存函数**:

```python
# 修改位置：行号 141-164
def save_upload_history(history: UploadHistory):
    """保存上传历史到数据库"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO upload_history
        (business_id, doc_number, doc_type, file_name, file_size, file_extension,
         status, error_code, error_message, yonyou_file_id, retry_count)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        history.business_id,
        history.doc_number,      # 新增
        history.doc_type,        # 新增
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

**注意**: `upload_single_file()` 是内部嵌套函数，需要通过闭包访问外部的doc_number和doc_type变量。

#### 3.2.3 模型类更新

**修改文件**: `/Users/lichuansong/Desktop/projects/单据上传管理/app/models/upload_history.py`

**变更位置**: UploadHistory类构造函数

**变更后**:
```python
from datetime import datetime
from typing import Optional


class UploadHistory:
    def __init__(
        self,
        id: Optional[int] = None,
        business_id: str = "",
        doc_number: Optional[str] = None,      # 新增
        doc_type: Optional[str] = None,        # 新增
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
        self.doc_number = doc_number        # 新增
        self.doc_type = doc_type            # 新增
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

---

### 3.3 新增管理API接口

#### 3.3.1 创建管理API路由

**新建文件**: `/Users/lichuansong/Desktop/projects/单据上传管理/app/api/admin.py`

**完整代码**:
```python
from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import StreamingResponse
from typing import List, Dict, Any, Optional
from datetime import datetime
import csv
import io
from app.core.database import get_db_connection

router = APIRouter()


@router.get("/records")
async def get_admin_records(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页记录数"),
    search: Optional[str] = Query(None, description="搜索关键词（单据编号/类型）"),
    doc_type: Optional[str] = Query(None, description="单据类型筛选"),
    start_date: Optional[str] = Query(None, description="开始日期（YYYY-MM-DD）"),
    end_date: Optional[str] = Query(None, description="结束日期（YYYY-MM-DD）")
) -> Dict[str, Any]:
    """
    获取上传记录列表（管理页面）

    查询参数:
    - page: 页码（从1开始）
    - page_size: 每页记录数（默认20，最大100）
    - search: 搜索关键词（模糊匹配单据编号或文件名）
    - doc_type: 单据类型筛选（销售/转库/其他）
    - start_date: 开始日期（格式：YYYY-MM-DD）
    - end_date: 结束日期（格式：YYYY-MM-DD）

    响应格式:
    {
        "total": 150,
        "page": 1,
        "page_size": 20,
        "total_pages": 8,
        "records": [...]
    }
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # 构建WHERE条件
    where_clauses = []
    params = []

    if search:
        where_clauses.append("(doc_number LIKE ? OR file_name LIKE ?)")
        search_pattern = f"%{search}%"
        params.extend([search_pattern, search_pattern])

    if doc_type:
        where_clauses.append("doc_type = ?")
        params.append(doc_type)

    if start_date:
        where_clauses.append("DATE(upload_time) >= ?")
        params.append(start_date)

    if end_date:
        where_clauses.append("DATE(upload_time) <= ?")
        params.append(end_date)

    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

    # 查询总记录数
    cursor.execute(f"SELECT COUNT(*) FROM upload_history WHERE {where_sql}", params)
    total = cursor.fetchone()[0]

    # 计算分页
    total_pages = (total + page_size - 1) // page_size
    offset = (page - 1) * page_size

    # 查询分页数据
    cursor.execute(f"""
        SELECT id, business_id, doc_number, doc_type, file_name, file_size,
               upload_time, status, error_message
        FROM upload_history
        WHERE {where_sql}
        ORDER BY upload_time DESC
        LIMIT ? OFFSET ?
    """, params + [page_size, offset])

    rows = cursor.fetchall()
    conn.close()

    # 转换为字典列表
    records = []
    for row in rows:
        records.append({
            "id": row[0],
            "business_id": row[1],
            "doc_number": row[2],
            "doc_type": row[3],
            "file_name": row[4],
            "file_size": row[5],
            "upload_time": row[6],
            "status": row[7],
            "error_message": row[8]
        })

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "records": records
    }


@router.get("/export")
async def export_records(
    search: Optional[str] = Query(None, description="搜索关键词"),
    doc_type: Optional[str] = Query(None, description="单据类型筛选"),
    start_date: Optional[str] = Query(None, description="开始日期"),
    end_date: Optional[str] = Query(None, description="结束日期")
):
    """
    导出上传记录为CSV

    查询参数: 与/records接口相同（不包含分页参数）

    响应: CSV文件流
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # 构建WHERE条件（复用逻辑）
    where_clauses = []
    params = []

    if search:
        where_clauses.append("(doc_number LIKE ? OR file_name LIKE ?)")
        search_pattern = f"%{search}%"
        params.extend([search_pattern, search_pattern])

    if doc_type:
        where_clauses.append("doc_type = ?")
        params.append(doc_type)

    if start_date:
        where_clauses.append("DATE(upload_time) >= ?")
        params.append(start_date)

    if end_date:
        where_clauses.append("DATE(upload_time) <= ?")
        params.append(end_date)

    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

    # 查询所有匹配记录
    cursor.execute(f"""
        SELECT doc_number, doc_type, business_id, upload_time, file_name,
               file_size, status, error_message
        FROM upload_history
        WHERE {where_sql}
        ORDER BY upload_time DESC
    """, params)

    rows = cursor.fetchall()
    conn.close()

    # 生成CSV
    output = io.StringIO()
    writer = csv.writer(output)

    # 写入表头
    writer.writerow([
        "单据编号", "单据类型", "业务ID", "上传时间",
        "文件名", "文件大小(字节)", "状态", "错误信息"
    ])

    # 写入数据
    for row in rows:
        writer.writerow(row)

    # 重置指针
    output.seek(0)

    # 返回CSV流
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=upload_records_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        }
    )


@router.get("/statistics")
async def get_statistics() -> Dict[str, Any]:
    """
    获取统计数据

    响应格式:
    {
        "total_uploads": 1500,
        "success_count": 1450,
        "failed_count": 50,
        "by_doc_type": {
            "销售": 800,
            "转库": 600,
            "其他": 100
        }
    }
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # 总上传数和成功/失败数
    cursor.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success,
            SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed
        FROM upload_history
    """)
    row = cursor.fetchone()
    total_uploads = row[0]
    success_count = row[1]
    failed_count = row[2]

    # 按单据类型统计
    cursor.execute("""
        SELECT doc_type, COUNT(*) as count
        FROM upload_history
        WHERE doc_type IS NOT NULL
        GROUP BY doc_type
    """)

    by_doc_type = {}
    for row in cursor.fetchall():
        by_doc_type[row[0]] = row[1]

    conn.close()

    return {
        "total_uploads": total_uploads,
        "success_count": success_count,
        "failed_count": failed_count,
        "by_doc_type": by_doc_type
    }
```

#### 3.3.2 注册管理路由

**修改文件**: `/Users/lichuansong/Desktop/projects/单据上传管理/app/main.py`

**新增导入**:
```python
from app.api import upload, history, admin  # 新增admin
```

**新增路由注册**:
```python
# 在行号30后添加
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
```

**完整路由注册代码**:
```python
# 路由
app.include_router(upload.router, prefix="/api", tags=["upload"])
app.include_router(history.router, prefix="/api", tags=["history"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
```

---

### 3.4 前端上传页面改造

#### 3.4.1 JavaScript URL解析改造

**修改文件**: `/Users/lichuansong/Desktop/projects/单据上传管理/app/static/js/app.js`

**修改位置1: 全局状态定义**

```javascript
// 行号 2-10，修改state对象
const state = {
    businessId: '',
    docNumber: '',      // 新增
    docType: '',        // 新增
    selectedFiles: [],
    maxFiles: 10,
    maxFileSize: 10 * 1024 * 1024,
    uploading: false,
    validating: false,
    fileValidationStatus: new Map()
};
```

**修改位置2: init()函数 - URL参数提取**

```javascript
// 行号 34-54，修改init函数
function init() {
    // 从URL查询参数提取参数
    const urlParams = new URLSearchParams(window.location.search);
    state.businessId = urlParams.get('business_id');
    state.docNumber = urlParams.get('doc_number');
    state.docType = urlParams.get('doc_type');

    // 验证必填参数
    if (!state.businessId || !/^\d+$/.test(state.businessId)) {
        showToast('错误的业务单据ID，请扫描正确的二维码', 'error');
        return;
    }

    if (!state.docNumber || state.docNumber.trim().length === 0) {
        showToast('缺少单据编号参数', 'error');
        return;
    }

    if (!state.docType || !['销售', '转库', '其他'].includes(state.docType)) {
        showToast('单据类型参数错误', 'error');
        return;
    }

    // 显示参数信息
    elements.businessIdDisplay.textContent = `${state.docType} - ${state.docNumber}`;

    // 根据单据类型设置主题色（可选）
    setThemeByDocType(state.docType);

    // 绑定事件
    elements.uploadArea.addEventListener('click', () => elements.fileInput.click());
    elements.fileInput.addEventListener('change', handleFileSelect);
    elements.btnClear.addEventListener('click', clearFiles);
    elements.btnUpload.addEventListener('click', uploadFiles);
    elements.btnHistory.addEventListener('click', showHistory);
    elements.btnCloseModal.addEventListener('click', () => elements.historyModal.style.display = 'none');
}

// 新增函数：根据单据类型设置主题
function setThemeByDocType(docType) {
    const header = document.querySelector('.header');

    // 移除现有主题类
    header.classList.remove('theme-sales', 'theme-transfer', 'theme-other');

    // 根据类型添加主题类
    if (docType === '销售') {
        header.classList.add('theme-sales');
    } else if (docType === '转库') {
        header.classList.add('theme-transfer');
    } else {
        header.classList.add('theme-other');
    }
}
```

**修改位置3: uploadFiles()函数 - 表单数据提交**

```javascript
// 行号 224-230，修改FormData构建
// 准备FormData
const formData = new FormData();
formData.append('business_id', state.businessId);
formData.append('doc_number', state.docNumber);    // 新增
formData.append('doc_type', state.docType);        // 新增
state.selectedFiles.forEach(file => {
    formData.append('files', file);
});
```

**修改位置4: 二维码验证 - URL提取逻辑**

```javascript
// 行号 477-481，修改extractBusinessId函数
function extractBusinessId(url) {
    // 新格式: http://xxx:port/?business_id=数字&doc_number=xx&doc_type=xx
    try {
        const urlObj = new URL(url);
        const businessId = urlObj.searchParams.get('business_id');
        const docNumber = urlObj.searchParams.get('doc_number');
        const docType = urlObj.searchParams.get('doc_type');

        // 验证business_id格式
        if (businessId && /^\d+$/.test(businessId)) {
            return {
                businessId: businessId,
                docNumber: docNumber,
                docType: docType
            };
        }
        return null;
    } catch (e) {
        // URL解析失败
        return null;
    }
}
```

**修改位置5: 二维码验证 - 比对逻辑**

```javascript
// 行号 420-456，修改validateQRCode函数中的比对部分
// 提取二维码内容
const detectedUrl = code.data;
const detectedParams = extractBusinessId(detectedUrl);
const currentBusinessId = state.businessId;
const currentDocNumber = state.docNumber;

if (!detectedParams) {
    // 二维码内容不是有效URL
    resolve({
        qrCodeDetected: true,
        urlMatched: false,
        detectedUrl: detectedUrl,
        needsUserConfirmation: true,
        message: '二维码内容格式不正确'
    });
    return;
}

if (detectedParams.businessId === currentBusinessId &&
    detectedParams.docNumber === currentDocNumber) {
    // 验证通过
    resolve({
        qrCodeDetected: true,
        urlMatched: true,
        detectedUrl: detectedUrl,
        needsUserConfirmation: false
    });
} else {
    // URL不匹配
    resolve({
        qrCodeDetected: true,
        urlMatched: false,
        detectedUrl: detectedUrl,
        detectedBusinessId: detectedParams.businessId,
        detectedDocNumber: detectedParams.docNumber,
        currentBusinessId: currentBusinessId,
        currentDocNumber: currentDocNumber,
        needsUserConfirmation: true,
        message: '二维码与当前单据不一致'
    });
}
```

**修改位置6: 验证对话框显示优化**

```javascript
// 行号 540-556，修改showValidationDialog函数中的URL比对显示
} else if (!result.urlMatched) {
    const currentUrl = `${window.location.origin}/?business_id=${result.currentBusinessId || state.businessId}&doc_number=${result.currentDocNumber || state.docNumber}&doc_type=${state.docType}`;
    message = `
        <div class="dialog-icon warning">⚠️</div>
        <h3>二维码不匹配</h3>
        <p>检测到的二维码与当前单据不一致</p>
        <div class="url-compare">
            <div class="url-item">
                <span class="label">图片单据:</span>
                <span class="url">${result.detectedDocNumber || '未知'}</span>
            </div>
            <div class="url-item">
                <span class="label">当前单据:</span>
                <span class="url">${result.currentDocNumber || state.docNumber}</span>
            </div>
        </div>
    `;
}
```

#### 3.4.2 HTML界面文本调整

**修改文件**: `/Users/lichuansong/Desktop/projects/单据上传管理/app/static/index.html`

**修改位置**: 头部显示区域

```html
<!-- 行号 13-16 -->
<header class="header">
    <h1>单据上传</h1>
    <p class="business-id">单据信息: <span id="businessIdDisplay">--</span></p>
</header>
```

#### 3.4.3 CSS样式新增

**修改文件**: `/Users/lichuansong/Desktop/projects/单据上传管理/app/static/css/style.css`

**新增主题样式**（文件末尾添加）:

```css
/* 单据类型主题色 */
.header.theme-sales {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.header.theme-transfer {
    background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
}

.header.theme-other {
    background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
}
```

---

### 3.5 新增管理页面

#### 3.5.1 创建管理页面HTML

**新建文件**: `/Users/lichuansong/Desktop/projects/单据上传管理/app/static/admin.html`

**完整代码**:
```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>上传记录管理 - 单据上传系统</title>
    <link rel="stylesheet" href="/static/css/admin.css">
</head>
<body>
    <div class="admin-container">
        <!-- 头部 -->
        <header class="admin-header">
            <h1>上传记录管理</h1>
            <div class="header-actions">
                <button class="btn-refresh" id="btnRefresh">刷新</button>
                <button class="btn-export" id="btnExport">导出CSV</button>
            </div>
        </header>

        <!-- 统计卡片 -->
        <div class="stats-section" id="statsSection">
            <div class="stat-card">
                <div class="stat-label">总上传数</div>
                <div class="stat-value" id="statTotal">0</div>
            </div>
            <div class="stat-card success">
                <div class="stat-label">成功</div>
                <div class="stat-value" id="statSuccess">0</div>
            </div>
            <div class="stat-card error">
                <div class="stat-label">失败</div>
                <div class="stat-value" id="statFailed">0</div>
            </div>
        </div>

        <!-- 筛选栏 -->
        <div class="filter-section">
            <div class="filter-row">
                <input
                    type="text"
                    id="searchInput"
                    class="search-input"
                    placeholder="搜索单据编号或文件名"
                >

                <select id="docTypeFilter" class="filter-select">
                    <option value="">全部类型</option>
                    <option value="销售">销售</option>
                    <option value="转库">转库</option>
                    <option value="其他">其他</option>
                </select>

                <input
                    type="date"
                    id="startDateInput"
                    class="date-input"
                    placeholder="开始日期"
                >

                <input
                    type="date"
                    id="endDateInput"
                    class="date-input"
                    placeholder="结束日期"
                >

                <button class="btn-search" id="btnSearch">搜索</button>
                <button class="btn-reset" id="btnReset">重置</button>
            </div>
        </div>

        <!-- 数据表格 -->
        <div class="table-section">
            <table class="data-table">
                <thead>
                    <tr>
                        <th>单据编号</th>
                        <th>单据类型</th>
                        <th>业务ID</th>
                        <th>上传时间</th>
                        <th>文件名</th>
                        <th>大小</th>
                        <th>状态</th>
                    </tr>
                </thead>
                <tbody id="tableBody">
                    <!-- 数据行动态插入 -->
                </tbody>
            </table>

            <!-- 空状态 -->
            <div class="empty-state" id="emptyState" style="display: none;">
                <p>暂无记录</p>
            </div>

            <!-- 加载状态 -->
            <div class="loading-state" id="loadingState" style="display: none;">
                <div class="spinner"></div>
                <p>加载中...</p>
            </div>
        </div>

        <!-- 分页 -->
        <div class="pagination-section">
            <div class="pagination-info">
                共 <span id="totalRecords">0</span> 条记录，
                第 <span id="currentPage">1</span> / <span id="totalPages">1</span> 页
            </div>
            <div class="pagination-controls">
                <button class="btn-page" id="btnFirstPage">首页</button>
                <button class="btn-page" id="btnPrevPage">上一页</button>
                <button class="btn-page" id="btnNextPage">下一页</button>
                <button class="btn-page" id="btnLastPage">末页</button>
            </div>
        </div>
    </div>

    <!-- Toast提示 -->
    <div class="toast" id="toast"></div>

    <script src="/static/js/admin.js"></script>
</body>
</html>
```

#### 3.5.2 创建管理页面CSS

**新建文件**: `/Users/lichuansong/Desktop/projects/单据上传管理/app/static/css/admin.css`

**完整代码**:
```css
* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    background: #f5f7fa;
    color: #333;
}

.admin-container {
    max-width: 1400px;
    margin: 0 auto;
    padding: 20px;
}

/* 头部 */
.admin-header {
    background: white;
    padding: 20px 30px;
    border-radius: 8px;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 20px;
}

.admin-header h1 {
    font-size: 24px;
    color: #2c3e50;
}

.header-actions {
    display: flex;
    gap: 10px;
}

.btn-refresh, .btn-export {
    padding: 10px 20px;
    border: none;
    border-radius: 6px;
    font-size: 14px;
    cursor: pointer;
    transition: all 0.3s;
}

.btn-refresh {
    background: #3498db;
    color: white;
}

.btn-refresh:hover {
    background: #2980b9;
}

.btn-export {
    background: #27ae60;
    color: white;
}

.btn-export:hover {
    background: #229954;
}

/* 统计卡片 */
.stats-section {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 20px;
    margin-bottom: 20px;
}

.stat-card {
    background: white;
    padding: 20px;
    border-radius: 8px;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    border-left: 4px solid #3498db;
}

.stat-card.success {
    border-left-color: #27ae60;
}

.stat-card.error {
    border-left-color: #e74c3c;
}

.stat-label {
    font-size: 14px;
    color: #7f8c8d;
    margin-bottom: 10px;
}

.stat-value {
    font-size: 32px;
    font-weight: bold;
    color: #2c3e50;
}

/* 筛选栏 */
.filter-section {
    background: white;
    padding: 20px;
    border-radius: 8px;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    margin-bottom: 20px;
}

.filter-row {
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
}

.search-input, .filter-select, .date-input {
    padding: 10px;
    border: 1px solid #ddd;
    border-radius: 6px;
    font-size: 14px;
    flex: 1;
    min-width: 150px;
}

.search-input {
    flex: 2;
}

.btn-search, .btn-reset {
    padding: 10px 20px;
    border: none;
    border-radius: 6px;
    font-size: 14px;
    cursor: pointer;
    transition: all 0.3s;
}

.btn-search {
    background: #3498db;
    color: white;
}

.btn-search:hover {
    background: #2980b9;
}

.btn-reset {
    background: #95a5a6;
    color: white;
}

.btn-reset:hover {
    background: #7f8c8d;
}

/* 数据表格 */
.table-section {
    background: white;
    border-radius: 8px;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    overflow: hidden;
    margin-bottom: 20px;
    min-height: 400px;
    position: relative;
}

.data-table {
    width: 100%;
    border-collapse: collapse;
}

.data-table thead {
    background: #f8f9fa;
}

.data-table th {
    padding: 15px;
    text-align: left;
    font-weight: 600;
    color: #2c3e50;
    border-bottom: 2px solid #dee2e6;
}

.data-table td {
    padding: 12px 15px;
    border-bottom: 1px solid #f1f1f1;
}

.data-table tbody tr:hover {
    background: #f8f9fa;
}

.status-badge {
    display: inline-block;
    padding: 4px 12px;
    border-radius: 12px;
    font-size: 12px;
    font-weight: 600;
}

.status-badge.success {
    background: #d4edda;
    color: #155724;
}

.status-badge.failed {
    background: #f8d7da;
    color: #721c24;
}

.file-name {
    max-width: 200px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.file-name:hover {
    overflow: visible;
    white-space: normal;
    word-break: break-all;
}

/* 空状态 */
.empty-state {
    text-align: center;
    padding: 60px 20px;
    color: #95a5a6;
}

.empty-state p {
    font-size: 16px;
}

/* 加载状态 */
.loading-state {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    text-align: center;
}

.spinner {
    width: 40px;
    height: 40px;
    border: 4px solid #f3f3f3;
    border-top: 4px solid #3498db;
    border-radius: 50%;
    animation: spin 1s linear infinite;
    margin: 0 auto 10px;
}

@keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
}

/* 分页 */
.pagination-section {
    background: white;
    padding: 15px 20px;
    border-radius: 8px;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.pagination-info {
    font-size: 14px;
    color: #7f8c8d;
}

.pagination-controls {
    display: flex;
    gap: 10px;
}

.btn-page {
    padding: 8px 16px;
    border: 1px solid #ddd;
    background: white;
    border-radius: 4px;
    font-size: 14px;
    cursor: pointer;
    transition: all 0.3s;
}

.btn-page:hover:not(:disabled) {
    background: #3498db;
    color: white;
    border-color: #3498db;
}

.btn-page:disabled {
    cursor: not-allowed;
    opacity: 0.5;
}

/* Toast */
.toast {
    position: fixed;
    top: 20px;
    right: 20px;
    padding: 15px 25px;
    background: #2c3e50;
    color: white;
    border-radius: 6px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    display: none;
    z-index: 9999;
}

.toast.success {
    background: #27ae60;
}

.toast.error {
    background: #e74c3c;
}

.toast.warning {
    background: #f39c12;
}

/* 响应式 */
@media (max-width: 768px) {
    .filter-row {
        flex-direction: column;
    }

    .search-input, .filter-select, .date-input {
        width: 100%;
    }

    .pagination-section {
        flex-direction: column;
        gap: 15px;
    }

    .data-table {
        font-size: 12px;
    }

    .data-table th,
    .data-table td {
        padding: 8px;
    }
}
```

#### 3.5.3 创建管理页面JavaScript

**新建文件**: `/Users/lichuansong/Desktop/projects/单据上传管理/app/static/js/admin.js`

**完整代码**:
```javascript
// 全局状态
const state = {
    currentPage: 1,
    pageSize: 20,
    totalPages: 1,
    totalRecords: 0,
    filters: {
        search: '',
        docType: '',
        startDate: '',
        endDate: ''
    }
};

// DOM元素
const elements = {
    // 统计
    statTotal: document.getElementById('statTotal'),
    statSuccess: document.getElementById('statSuccess'),
    statFailed: document.getElementById('statFailed'),

    // 筛选
    searchInput: document.getElementById('searchInput'),
    docTypeFilter: document.getElementById('docTypeFilter'),
    startDateInput: document.getElementById('startDateInput'),
    endDateInput: document.getElementById('endDateInput'),
    btnSearch: document.getElementById('btnSearch'),
    btnReset: document.getElementById('btnReset'),

    // 表格
    tableBody: document.getElementById('tableBody'),
    emptyState: document.getElementById('emptyState'),
    loadingState: document.getElementById('loadingState'),

    // 分页
    totalRecordsSpan: document.getElementById('totalRecords'),
    currentPageSpan: document.getElementById('currentPage'),
    totalPagesSpan: document.getElementById('totalPages'),
    btnFirstPage: document.getElementById('btnFirstPage'),
    btnPrevPage: document.getElementById('btnPrevPage'),
    btnNextPage: document.getElementById('btnNextPage'),
    btnLastPage: document.getElementById('btnLastPage'),

    // 操作
    btnRefresh: document.getElementById('btnRefresh'),
    btnExport: document.getElementById('btnExport'),

    // Toast
    toast: document.getElementById('toast')
};

// 初始化
function init() {
    // 绑定事件
    elements.btnSearch.addEventListener('click', handleSearch);
    elements.btnReset.addEventListener('click', handleReset);
    elements.btnRefresh.addEventListener('click', () => loadRecords());
    elements.btnExport.addEventListener('click', handleExport);

    elements.btnFirstPage.addEventListener('click', () => goToPage(1));
    elements.btnPrevPage.addEventListener('click', () => goToPage(state.currentPage - 1));
    elements.btnNextPage.addEventListener('click', () => goToPage(state.currentPage + 1));
    elements.btnLastPage.addEventListener('click', () => goToPage(state.totalPages));

    // 回车搜索
    elements.searchInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') handleSearch();
    });

    // 加载数据
    loadStatistics();
    loadRecords();
}

// 加载统计数据
async function loadStatistics() {
    try {
        const response = await fetch('/api/admin/statistics');
        const data = await response.json();

        elements.statTotal.textContent = data.total_uploads;
        elements.statSuccess.textContent = data.success_count;
        elements.statFailed.textContent = data.failed_count;

    } catch (error) {
        console.error('加载统计数据失败:', error);
    }
}

// 加载记录列表
async function loadRecords() {
    // 显示加载状态
    elements.loadingState.style.display = 'block';
    elements.emptyState.style.display = 'none';
    elements.tableBody.innerHTML = '';

    try {
        // 构建查询参数
        const params = new URLSearchParams({
            page: state.currentPage,
            page_size: state.pageSize
        });

        if (state.filters.search) params.append('search', state.filters.search);
        if (state.filters.docType) params.append('doc_type', state.filters.docType);
        if (state.filters.startDate) params.append('start_date', state.filters.startDate);
        if (state.filters.endDate) params.append('end_date', state.filters.endDate);

        const response = await fetch(`/api/admin/records?${params}`);
        const data = await response.json();

        // 更新状态
        state.totalRecords = data.total;
        state.totalPages = data.total_pages;
        state.currentPage = data.page;

        // 隐藏加载状态
        elements.loadingState.style.display = 'none';

        // 显示数据或空状态
        if (data.records.length === 0) {
            elements.emptyState.style.display = 'block';
        } else {
            renderTable(data.records);
        }

        // 更新分页信息
        updatePagination();

    } catch (error) {
        elements.loadingState.style.display = 'none';
        showToast('加载数据失败: ' + error.message, 'error');
    }
}

// 渲染表格
function renderTable(records) {
    elements.tableBody.innerHTML = records.map(record => `
        <tr>
            <td>${record.doc_number || '-'}</td>
            <td>${record.doc_type || '-'}</td>
            <td>${record.business_id}</td>
            <td>${formatDateTime(record.upload_time)}</td>
            <td class="file-name" title="${record.file_name}">${record.file_name}</td>
            <td>${formatFileSize(record.file_size)}</td>
            <td>
                <span class="status-badge ${record.status}">
                    ${record.status === 'success' ? '成功' : '失败'}
                </span>
                ${record.error_message ? `<br><small style="color: #e74c3c;">${record.error_message}</small>` : ''}
            </td>
        </tr>
    `).join('');
}

// 更新分页信息
function updatePagination() {
    elements.totalRecordsSpan.textContent = state.totalRecords;
    elements.currentPageSpan.textContent = state.currentPage;
    elements.totalPagesSpan.textContent = state.totalPages;

    // 更新按钮状态
    elements.btnFirstPage.disabled = state.currentPage === 1;
    elements.btnPrevPage.disabled = state.currentPage === 1;
    elements.btnNextPage.disabled = state.currentPage === state.totalPages;
    elements.btnLastPage.disabled = state.currentPage === state.totalPages;
}

// 跳转页面
function goToPage(page) {
    if (page < 1 || page > state.totalPages) return;
    state.currentPage = page;
    loadRecords();
}

// 处理搜索
function handleSearch() {
    state.filters.search = elements.searchInput.value.trim();
    state.filters.docType = elements.docTypeFilter.value;
    state.filters.startDate = elements.startDateInput.value;
    state.filters.endDate = elements.endDateInput.value;

    state.currentPage = 1; // 重置到第一页
    loadRecords();
}

// 处理重置
function handleReset() {
    elements.searchInput.value = '';
    elements.docTypeFilter.value = '';
    elements.startDateInput.value = '';
    elements.endDateInput.value = '';

    state.filters = {
        search: '',
        docType: '',
        startDate: '',
        endDate: ''
    };

    state.currentPage = 1;
    loadRecords();
}

// 处理导出
async function handleExport() {
    try {
        // 构建查询参数
        const params = new URLSearchParams();

        if (state.filters.search) params.append('search', state.filters.search);
        if (state.filters.docType) params.append('doc_type', state.filters.docType);
        if (state.filters.startDate) params.append('start_date', state.filters.startDate);
        if (state.filters.endDate) params.append('end_date', state.filters.endDate);

        // 下载CSV
        window.location.href = `/api/admin/export?${params}`;

        showToast('开始导出...', 'success');

    } catch (error) {
        showToast('导出失败: ' + error.message, 'error');
    }
}

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

// 格式化文件大小
function formatFileSize(bytes) {
    if (!bytes) return '-';
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1024 / 1024).toFixed(1) + ' MB';
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

// 启动应用
init();
```

#### 3.5.4 注册管理页面路由

**修改文件**: `/Users/lichuansong/Desktop/projects/单据上传管理/app/main.py`

**新增路由**（在根路由之后添加）:

```python
@app.get("/admin")
async def admin_page():
    """管理页面入口"""
    return FileResponse("app/static/admin.html")
```

---

## 4. 实现步骤清单

### Phase 1: 数据库迁移（独立部署）

**任务清单**:
- [ ] 修改 `app/core/database.py` 的 `init_database()` 函数
- [ ] 添加字段检查和迁移逻辑
- [ ] 创建新索引
- [ ] 运行数据库迁移测试

**验证方式**:
```bash
# 启动应用，检查数据库表结构
sqlite3 data/upload_management.db ".schema upload_history"
```

**预期结果**: 表中包含 `doc_number` 和 `doc_type` 字段

---

### Phase 2: 后端API改造（依赖Phase 1）

**任务清单**:
- [ ] 修改 `app/models/upload_history.py` 模型类
- [ ] 修改 `app/main.py` 根路由，支持查询参数
- [ ] 修改 `app/api/upload.py` 上传接口，接收新参数
- [ ] 修改数据库保存逻辑，存储新字段
- [ ] 创建 `app/api/admin.py` 管理API
- [ ] 在 `app/main.py` 注册管理API路由

**验证方式**:
```bash
# 测试新URL格式路由
curl "http://localhost:10000/?business_id=123456&doc_number=SO001&doc_type=销售"

# 测试上传API
curl -X POST http://localhost:10000/api/upload \
  -F "business_id=123456" \
  -F "doc_number=SO001" \
  -F "doc_type=销售" \
  -F "files=@test.jpg"

# 测试管理API
curl "http://localhost:10000/api/admin/records?page=1&page_size=20"
curl "http://localhost:10000/api/admin/statistics"
```

**预期结果**: 所有接口返回200状态码，数据格式正确

---

### Phase 3: 前端上传页面改造（依赖Phase 2）

**任务清单**:
- [ ] 修改 `app/static/js/app.js` 全局状态对象
- [ ] 修改 `init()` 函数，使用URLSearchParams解析查询参数
- [ ] 修改 `uploadFiles()` 函数，提交新字段
- [ ] 修改 `extractBusinessId()` 函数，支持新URL格式
- [ ] 修改 `validateQRCode()` 函数，比对新参数
- [ ] 修改 `showValidationDialog()` 函数，显示单据信息
- [ ] 修改 `app/static/index.html` 界面文本
- [ ] 新增 `app/static/css/style.css` 主题样式

**验证方式**:
```
访问: http://localhost:10000/?business_id=123456&doc_number=SO001&doc_type=销售
检查: 页面显示单据信息，上传功能正常
```

**预期结果**: 页面正常加载，显示单据信息，可上传文件

---

### Phase 4: 管理页面开发（依赖Phase 2）

**任务清单**:
- [ ] 创建 `app/static/admin.html` 页面结构
- [ ] 创建 `app/static/css/admin.css` 样式文件
- [ ] 创建 `app/static/js/admin.js` 逻辑文件
- [ ] 在 `app/main.py` 注册 `/admin` 路由
- [ ] 实现数据加载和分页
- [ ] 实现搜索和筛选功能
- [ ] 实现导出CSV功能
- [ ] 实现统计数据展示

**验证方式**:
```
访问: http://localhost:10000/admin
检查:
  - 统计卡片显示数据
  - 表格显示上传记录
  - 搜索筛选功能正常
  - 分页切换正常
  - 导出CSV成功下载
```

**预期结果**: 管理页面完整功能正常

---

### Phase 5: 集成测试与文档更新

**任务清单**:
- [ ] 更新单元测试用例（新增参数测试）
- [ ] 更新集成测试用例（端到端流程测试）
- [ ] 测试旧URL格式是否正确拒绝
- [ ] 测试二维码验证适配新格式
- [ ] 更新API文档（Swagger UI）
- [ ] 更新README.md使用说明
- [ ] 验证所有测试通过

**测试场景**:
1. 使用新URL格式上传文件 → 成功
2. 访问旧URL格式 `/{business_id}` → 返回404
3. 管理页面搜索单据编号 → 找到记录
4. 管理页面按类型筛选 → 过滤正确
5. 二维码验证新格式URL → 匹配成功

**预期结果**: 所有测试通过，文档更新完整

---

## 5. 验证计划

### 5.1 单元测试

**新增测试文件**: `/Users/lichuansong/Desktop/projects/单据上传管理/tests/test_admin_api.py`

**测试用例**:
```python
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_get_admin_records_default():
    """测试获取记录列表（默认参数）"""
    response = client.get("/api/admin/records")
    assert response.status_code == 200
    data = response.json()
    assert "total" in data
    assert "records" in data
    assert isinstance(data["records"], list)


def test_get_admin_records_with_filters():
    """测试带筛选条件的记录查询"""
    response = client.get("/api/admin/records?doc_type=销售&page=1&page_size=10")
    assert response.status_code == 200
    data = response.json()
    assert data["page"] == 1
    assert data["page_size"] == 10


def test_get_admin_records_search():
    """测试搜索功能"""
    response = client.get("/api/admin/records?search=SO001")
    assert response.status_code == 200


def test_export_records():
    """测试导出CSV"""
    response = client.get("/api/admin/export")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv; charset=utf-8"


def test_get_statistics():
    """测试统计数据"""
    response = client.get("/api/admin/statistics")
    assert response.status_code == 200
    data = response.json()
    assert "total_uploads" in data
    assert "success_count" in data
    assert "failed_count" in data
```

**修改现有测试**: `/Users/lichuansong/Desktop/projects/单据上传管理/tests/test_upload_api.py`

```python
def test_upload_files_with_new_params(client, sample_image_file):
    """测试新参数上传"""
    response = client.post(
        "/api/upload",
        data={
            "business_id": "123456",
            "doc_number": "SO20250103001",
            "doc_type": "销售"
        },
        files={"files": sample_image_file}
    )
    assert response.status_code == 200


def test_upload_files_missing_doc_number(client, sample_image_file):
    """测试缺少doc_number参数"""
    response = client.post(
        "/api/upload",
        data={
            "business_id": "123456",
            "doc_type": "销售"
        },
        files={"files": sample_image_file}
    )
    assert response.status_code == 422  # Validation error


def test_upload_files_invalid_doc_type(client, sample_image_file):
    """测试无效的doc_type"""
    response = client.post(
        "/api/upload",
        data={
            "business_id": "123456",
            "doc_number": "SO001",
            "doc_type": "无效类型"
        },
        files={"files": sample_image_file}
    )
    assert response.status_code == 400
```

### 5.2 集成测试

**测试场景**:

**场景1: 完整上传流程（新格式）**
```
1. 访问新格式URL
   GET /?business_id=123&doc_number=SO001&doc_type=销售
   → 返回index.html

2. 上传文件
   POST /api/upload
   Form: {business_id, doc_number, doc_type, files}
   → 成功返回

3. 查询数据库
   SELECT * FROM upload_history WHERE doc_number='SO001'
   → 记录存在，包含doc_number和doc_type

4. 管理页面查看
   GET /api/admin/records?search=SO001
   → 找到对应记录
```

**场景2: 旧URL格式拒绝**
```
1. 访问旧格式URL
   GET /123456
   → 返回404 Not Found
```

**场景3: 二维码验证（新格式）**
```
1. 上传包含新格式二维码的图片
   图片二维码内容: http://192.168.1.4:10000/?business_id=123&doc_number=SO001&doc_type=销售
   当前页面URL: http://192.168.1.4:10000/?business_id=123&doc_number=SO001&doc_type=销售
   → 验证通过

2. 上传不匹配的二维码
   图片二维码: business_id=456, doc_number=SO002
   当前页面: business_id=123, doc_number=SO001
   → 显示警告对话框
```

**场景4: 管理页面功能**
```
1. 访问管理页面
   GET /admin
   → 显示统计和表格

2. 搜索单据编号
   GET /api/admin/records?search=SO001
   → 返回匹配记录

3. 筛选单据类型
   GET /api/admin/records?doc_type=销售
   → 仅返回销售类型

4. 导出CSV
   GET /api/admin/export?doc_type=销售
   → 下载CSV文件
```

### 5.3 性能测试

**测试指标**:
- 管理页面首次加载: < 2秒
- 搜索响应时间: < 500ms
- 分页切换: < 300ms
- 导出1000条记录: < 3秒

**测试工具**: 使用浏览器开发者工具或Apache Bench

---

## 6. 回滚计划

### 6.1 数据库回滚

如果需要回滚数据库变更:

```sql
-- 删除新增字段
ALTER TABLE upload_history DROP COLUMN doc_number;
ALTER TABLE upload_history DROP COLUMN doc_type;

-- 删除新增索引
DROP INDEX IF EXISTS idx_doc_number;
DROP INDEX IF EXISTS idx_doc_type;
DROP INDEX IF EXISTS idx_doc_type_upload_time;
```

### 6.2 代码回滚

使用Git回滚到重构前的版本:

```bash
# 查看提交历史
git log --oneline

# 回滚到指定提交
git revert <commit-hash>

# 或者硬重置（慎用）
git reset --hard <commit-hash>
```

### 6.3 兼容性策略（不推荐，因需求明确不支持旧格式）

如果需要临时支持新旧格式:

```python
# app/main.py
@app.get("/{business_id}")
async def upload_page_legacy(business_id: str):
    """旧URL格式（已废弃）"""
    # 重定向到新格式（需要外部提供doc_number和doc_type）
    raise HTTPException(
        status_code=410,
        detail="此URL格式已废弃，请使用新格式: /?business_id=x&doc_number=x&doc_type=x"
    )

@app.get("/")
async def upload_page(
    business_id: str = Query(...),
    doc_number: str = Query(...),
    doc_type: str = Query(...)
):
    """新URL格式"""
    # 新格式处理逻辑
    pass
```

---

## 7. 潜在风险与缓解措施

### 7.1 风险识别

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|----------|
| 旧二维码失效 | 用户无法使用现有二维码 | 高 | 提前通知，更新二维码生成逻辑 |
| 前端参数解析失败 | 页面无法加载 | 中 | 添加完善的错误提示和降级处理 |
| 数据库迁移失败 | 应用无法启动 | 低 | 先在测试环境验证，做好备份 |
| 管理页面性能问题 | 大数据量时加载缓慢 | 中 | 优化SQL查询，添加索引，分页限制 |
| CSV导出内存溢出 | 导出大量数据时失败 | 低 | 使用流式响应，限制单次导出数量 |

### 7.2 缓解措施详细说明

**1. 旧二维码失效**
- 解决方案: 在用友云系统中批量更新二维码生成逻辑
- 过渡方案: 提供二维码转换工具或临时兼容接口

**2. 前端参数解析失败**
```javascript
// 添加完善的错误处理
function init() {
    try {
        const urlParams = new URLSearchParams(window.location.search);
        // ... 参数提取和验证
    } catch (error) {
        showToast('URL参数解析失败，请联系管理员', 'error');
        console.error('URL parse error:', error);
        // 可选：显示错误详情供调试
    }
}
```

**3. 数据库迁移失败**
```python
# 添加迁移前检查
def init_database():
    try:
        conn = get_db_connection()
        # 创建备份表
        cursor.execute("CREATE TABLE IF NOT EXISTS upload_history_backup AS SELECT * FROM upload_history")
        # 执行迁移
        # ...
        conn.commit()
    except Exception as e:
        conn.rollback()
        # 从备份恢复
        cursor.execute("DROP TABLE upload_history")
        cursor.execute("ALTER TABLE upload_history_backup RENAME TO upload_history")
        raise
```

**4. 管理页面性能优化**
```python
# 添加查询超时和结果限制
@router.get("/records")
async def get_admin_records(
    page_size: int = Query(20, ge=1, le=100)  # 最大100条
):
    # 添加查询超时（如使用asyncio.wait_for）
    pass
```

**5. CSV导出优化**
```python
# 使用生成器流式导出
def generate_csv_rows():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT ... FROM upload_history ORDER BY upload_time DESC LIMIT 10000")  # 限制最大导出数

    yield "单据编号,单据类型,...\n"  # 表头

    for row in cursor:
        yield ",".join(map(str, row)) + "\n"

    conn.close()

return StreamingResponse(generate_csv_rows(), media_type="text/csv")
```

---

## 8. 附录

### 8.1 URL格式对比

| 项目 | 旧格式 | 新格式 |
|------|--------|--------|
| 示例 | `http://192.168.1.4:10000/2372677039643688969` | `http://192.168.1.4:10000/?business_id=2372677039643688969&doc_number=SO20250103001&doc_type=销售` |
| 参数数量 | 1个 | 3个 |
| 参数类型 | 路径参数 | 查询参数 |
| 业务语义 | 仅用友云ID | 包含单据编号和类型 |
| 可扩展性 | 差（需要修改路由） | 好（可添加查询参数） |
| 二维码长度 | 短 | 长 |
| SEO友好 | 好 | 一般 |

### 8.2 数据库Schema变更对比

**变更前**:
```sql
CREATE TABLE upload_history (
    id INTEGER PRIMARY KEY,
    business_id VARCHAR(50) NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    file_size INTEGER NOT NULL,
    file_extension VARCHAR(20),
    upload_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) NOT NULL,
    error_code VARCHAR(50),
    error_message TEXT,
    yonyou_file_id VARCHAR(255),
    retry_count INTEGER DEFAULT 0
);
```

**变更后**:
```sql
CREATE TABLE upload_history (
    id INTEGER PRIMARY KEY,
    business_id VARCHAR(50) NOT NULL,
    doc_number VARCHAR(100),              -- 新增
    doc_type VARCHAR(20),                 -- 新增
    file_name VARCHAR(255) NOT NULL,
    file_size INTEGER NOT NULL,
    file_extension VARCHAR(20),
    upload_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) NOT NULL,
    error_code VARCHAR(50),
    error_message TEXT,
    yonyou_file_id VARCHAR(255),
    retry_count INTEGER DEFAULT 0
);

-- 新增索引
CREATE INDEX idx_doc_number ON upload_history(doc_number);
CREATE INDEX idx_doc_type ON upload_history(doc_type);
CREATE INDEX idx_doc_type_upload_time ON upload_history(doc_type, upload_time);
```

### 8.3 API接口列表

| 端点 | 方法 | 功能 | 状态 |
|------|------|------|------|
| `/` | GET | 上传页面（新格式） | 新增 |
| `/{business_id}` | GET | 上传页面（旧格式） | 废弃 |
| `/admin` | GET | 管理页面 | 新增 |
| `/api/upload` | POST | 文件上传 | 修改（新增参数） |
| `/api/history/{business_id}` | GET | 历史记录 | 保持不变 |
| `/api/admin/records` | GET | 管理记录列表 | 新增 |
| `/api/admin/export` | GET | 导出CSV | 新增 |
| `/api/admin/statistics` | GET | 统计数据 | 新增 |

### 8.4 文件变更清单

**修改文件**:
- `/Users/lichuansong/Desktop/projects/单据上传管理/app/core/database.py`
- `/Users/lichuansong/Desktop/projects/单据上传管理/app/models/upload_history.py`
- `/Users/lichuansong/Desktop/projects/单据上传管理/app/main.py`
- `/Users/lichuansong/Desktop/projects/单据上传管理/app/api/upload.py`
- `/Users/lichuansong/Desktop/projects/单据上传管理/app/static/js/app.js`
- `/Users/lichuansong/Desktop/projects/单据上传管理/app/static/index.html`
- `/Users/lichuansong/Desktop/projects/单据上传管理/app/static/css/style.css`

**新增文件**:
- `/Users/lichuansong/Desktop/projects/单据上传管理/app/api/admin.py`
- `/Users/lichuansong/Desktop/projects/单据上传管理/app/static/admin.html`
- `/Users/lichuansong/Desktop/projects/单据上传管理/app/static/css/admin.css`
- `/Users/lichuansong/Desktop/projects/单据上传管理/app/static/js/admin.js`
- `/Users/lichuansong/Desktop/projects/单据上传管理/tests/test_admin_api.py`

**删除文件**: 无

---

## 9. 总结

本技术规格文档提供了完整的URL格式重构和管理页面新增的实现方案，涵盖：

1. **数据库变更**: 新增doc_number和doc_type字段，优化索引
2. **后端改造**: 修改路由、上传API，新增管理API
3. **前端改造**: 适配查询参数、二维码验证逻辑
4. **管理页面**: 完整的数据展示、搜索、筛选、导出功能
5. **测试验证**: 详细的单元测试和集成测试方案
6. **风险控制**: 识别潜在风险并提供缓解措施

所有实现细节均基于现有代码库结构，遵循项目的编码规范和设计模式，确保实现的一致性和可维护性。

**下一步行动**: 按照实现步骤清单（Phase 1-5）依次执行，每个阶段完成后进行验证，确保功能正确性。

---

**文档状态**: ✅ 可直接用于代码生成
**审核状态**: 待技术负责人审核
**版本历史**: v1.0 (2025-10-03 初始版本)
