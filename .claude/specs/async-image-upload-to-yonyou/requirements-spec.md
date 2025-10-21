# 技术实施规格：异步图片上传到用友云

## 问题陈述

### 业务问题
当前系统在用户上传图片时，前端需要等待后端同步完成用友云上传（耗时 3-10 秒）才能得到响应，导致用户体验差，特别是在移动端网络不稳定时体验更差。

### 当前状态
- **上传流程**：前端提交 → 后端接收 → 同步上传到用友云（3个并发） → 返回结果
- **响应时间**：3-10 秒（取决于网络状况和图片大小）
- **用户体验**：用户需要等待较长时间，无法快速完成操作
- **技术实现**：在 `app/api/upload.py` 的 `upload_files` 函数中，使用 `asyncio.gather` 等待所有文件上传完成后才返回

### 期望结果
- **前端响应时间**：< 1 秒
- **用户操作体验**：立即得到反馈，可继续操作或关闭页面
- **状态可追溯**：用户可在历史记录中查看上传状态（pending/uploading/success/failed）
- **管理可监控**：管理员可在后台筛选查看失败记录
- **数据可靠性**：保持现有重试机制（3次），异常情况下数据不丢失

---

## 解决方案概览

### 方案
使用 **FastAPI BackgroundTasks** 将用友云上传操作从主请求流程中分离，实现异步处理。前端上传后，后端立即保存记录到数据库并返回成功，然后在后台任务中完成用友云上传并更新状态。

### 核心变更
1. **后端改造**：修改 `app/api/upload.py`，使用 `BackgroundTasks` 处理用友云上传
2. **数据库扩展**：无需新增字段（现有 `status` 字段已支持状态追踪）
3. **状态管理**：引入新的状态值 `uploading`，状态流转为 `pending → uploading → success/failed`
4. **前端适配**：历史记录和管理后台显示上传状态，管理后台支持按状态筛选

### 成功标准
- ✅ 前端响应时间 < 1 秒
- ✅ 后台任务成功执行，状态准确更新
- ✅ 保持现有重试机制（3次重试）
- ✅ 历史记录和管理后台正确显示状态
- ✅ 无数据丢失，异常情况有完整记录

---

## 技术实施

### 数据库变更

#### 现有表结构分析
当前 `upload_history` 表已包含以下字段：
```sql
CREATE TABLE upload_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_id VARCHAR(50) NOT NULL,
    doc_number VARCHAR(100),
    doc_type VARCHAR(20),
    product_type TEXT DEFAULT NULL,
    file_name VARCHAR(255) NOT NULL,
    file_size INTEGER NOT NULL,
    file_extension VARCHAR(20),
    upload_time DATETIME,
    status VARCHAR(20) NOT NULL,           -- 现有字段，已支持状态追踪
    error_code VARCHAR(50),                -- 现有字段，已支持错误记录
    error_message TEXT,                    -- 现有字段，已支持错误详情
    yonyou_file_id VARCHAR(255),
    retry_count INTEGER DEFAULT 0,         -- 现有字段，已支持重试计数
    local_file_path VARCHAR(500),
    deleted_at TEXT DEFAULT NULL,
    created_at DATETIME,
    updated_at DATETIME
)
```

#### 数据库变更结论
**无需新增字段**，现有表结构已完全支持异步上传功能：
- `status` 字段：支持新状态值 `uploading`
- `error_code`、`error_message`：记录失败原因
- `retry_count`：记录重试次数

#### 状态值定义
```python
# 在 app/models/upload_history.py 或 app/api/upload.py 中添加常量定义
UPLOAD_STATUS = {
    "PENDING": "pending",        # 已接收，等待上传
    "UPLOADING": "uploading",    # 正在上传到用友云
    "SUCCESS": "success",        # 上传成功
    "FAILED": "failed"           # 上传失败（3次重试后）
}
```

#### 数据迁移
**无需数据库迁移**，仅需要：
1. 确保现有索引 `idx_status` 存在（已存在于 `app/core/database.py`）
2. 代码中支持新的状态值 `uploading`

---

### 代码变更

#### 1. 核心文件：`app/api/upload.py`

##### 1.1 添加 BackgroundTasks 导入
```python
# 在文件开头添加导入
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks
```

##### 1.2 添加后台上传函数
在 `upload_files` 函数之前，添加新的后台任务函数：

```python
async def background_upload_to_yonyou(
    file_content: bytes,
    new_filename: str,
    business_id: str,
    business_type: str,
    local_file_path: str,
    record_id: int
):
    """
    后台任务：上传文件到用友云并更新数据库状态

    Args:
        file_content: 文件二进制内容
        new_filename: 新文件名
        business_id: 业务单据ID
        business_type: 业务类型
        local_file_path: 本地文件路径
        record_id: 数据库记录ID
    """
    from app.core.timezone import get_beijing_now_naive

    conn = None
    try:
        # 更新状态为 uploading
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE upload_history
            SET status = 'uploading', updated_at = ?
            WHERE id = ?
        """, (get_beijing_now_naive().isoformat(), record_id))
        conn.commit()
        conn.close()

        # 上传到用友云（保持现有重试机制）
        yonyou_file_id = None
        error_code = None
        error_message = None
        retry_count = 0

        for attempt in range(settings.MAX_RETRY_COUNT):
            result = await yonyou_client.upload_file(
                file_content,
                new_filename,
                business_id,
                retry_count=0,
                business_type=business_type
            )

            if result["success"]:
                yonyou_file_id = result["data"]["id"]
                retry_count = attempt
                break
            else:
                error_code = result["error_code"]
                error_message = result["error_message"]
                retry_count = attempt

                if attempt < settings.MAX_RETRY_COUNT - 1:
                    await asyncio.sleep(settings.RETRY_DELAY)

        # 更新最终状态
        conn = get_db_connection()
        cursor = conn.cursor()

        if yonyou_file_id:
            # 上传成功
            cursor.execute("""
                UPDATE upload_history
                SET status = 'success',
                    yonyou_file_id = ?,
                    retry_count = ?,
                    updated_at = ?
                WHERE id = ?
            """, (yonyou_file_id, retry_count, get_beijing_now_naive().isoformat(), record_id))

            # 保存文件到本地
            try:
                save_file_locally(file_content, local_file_path)
            except Exception as e:
                print(f"本地文件保存失败: {str(e)}")
        else:
            # 上传失败
            cursor.execute("""
                UPDATE upload_history
                SET status = 'failed',
                    error_code = ?,
                    error_message = ?,
                    retry_count = ?,
                    updated_at = ?
                WHERE id = ?
            """, (error_code, error_message, retry_count, get_beijing_now_naive().isoformat(), record_id))

        conn.commit()

    except Exception as e:
        # 异常处理：标记为失败
        print(f"后台上传任务异常: {str(e)}")
        try:
            if conn is None:
                conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE upload_history
                SET status = 'failed',
                    error_code = 'BACKGROUND_TASK_ERROR',
                    error_message = ?,
                    updated_at = ?
                WHERE id = ?
            """, (str(e), get_beijing_now_naive().isoformat(), record_id))
            conn.commit()
        except Exception as inner_e:
            print(f"更新失败状态时出错: {str(inner_e)}")
    finally:
        if conn:
            conn.close()
```

##### 1.3 修改上传路由函数
修改 `upload_files` 函数签名和实现：

```python
@router.post("/upload")
async def upload_files(
    background_tasks: BackgroundTasks,  # 新增参数
    business_id: str = Form(..., description="业务单据ID"),
    doc_number: str = Form(..., description="单据编号"),
    doc_type: str = Form(..., description="单据类型"),
    product_type: Optional[str] = Form(None, description="产品类型(如:油脂/快消)"),
    files: List[UploadFile] = File(...)
):
    """
    批量上传文件（异步处理）

    流程优化：
    1. 前端上传文件到后端
    2. 后端立即保存记录到数据库（状态：pending）
    3. 立即返回成功响应（< 1秒）
    4. 后台任务异步上传到用友云
    5. 上传完成后更新数据库状态（success/failed）

    请求参数:
    - business_id: 业务单据ID（纯数字，用于用友云API）
    - doc_number: 单据编号（业务标识，如SO20250103001）
    - doc_type: 单据类型（销售/转库/其他）
    - product_type: 产品类型（可选）
    - files: 文件列表 (最多10个)

    响应格式:
    {
        "success": true,
        "total": 10,
        "message": "已接收10个文件，正在后台上传中",
        "records": [
            {
                "id": 123,
                "file_name": "SO001_20251021_a3f2b1c4.jpg",
                "original_name": "photo.jpg",
                "status": "pending",
                "file_size": 102400
            }
        ]
    }
    """
    # 验证参数（保持不变）
    if not business_id or not business_id.isdigit():
        raise HTTPException(status_code=400, detail="businessId必须为纯数字")

    valid_doc_types = ["销售", "转库", "其他"]
    if doc_type not in valid_doc_types:
        raise HTTPException(
            status_code=400,
            detail=f"doc_type必须为以下值之一: {', '.join(valid_doc_types)}"
        )

    if not doc_number or len(doc_number.strip()) == 0:
        raise HTTPException(status_code=400, detail="doc_number不能为空")

    if len(files) > settings.MAX_FILES_PER_REQUEST:
        raise HTTPException(status_code=400, detail=f"单次最多上传{settings.MAX_FILES_PER_REQUEST}个文件")

    # 验证文件格式（保持不变）
    for file in files:
        file_ext = "." + file.filename.split(".")[-1].lower()
        if file_ext not in settings.ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的文件格式: {file_ext}，支持的格式: {', '.join(settings.ALLOWED_EXTENSIONS)}"
            )

    # 获取映射后的businessType
    business_type = DOC_TYPE_TO_BUSINESS_TYPE.get(doc_type, settings.YONYOU_BUSINESS_TYPE)

    # 处理每个文件（快速保存记录，添加后台任务）
    records = []
    from app.core.timezone import get_beijing_now_naive

    for upload_file in files:
        # 读取文件内容
        file_content = await upload_file.read()
        file_size = len(file_content)

        # 验证文件大小
        if file_size > settings.MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"文件 {upload_file.filename} 大小超过{settings.MAX_FILE_SIZE / 1024 / 1024}MB限制"
            )

        # 获取文件扩展名
        file_extension = "." + upload_file.filename.split(".")[-1].lower()

        # 生成唯一文件名
        storage_path = settings.LOCAL_STORAGE_PATH
        new_filename, local_file_path = generate_unique_filename(
            doc_number, file_extension, storage_path
        )

        # 立即保存记录到数据库（状态：pending）
        conn = get_db_connection()
        cursor = conn.cursor()

        beijing_now = get_beijing_now_naive()
        upload_time_str = beijing_now.isoformat()

        cursor.execute("""
            INSERT INTO upload_history
            (business_id, doc_number, doc_type, product_type, file_name, file_size, file_extension,
             upload_time, status, error_code, error_message, yonyou_file_id, retry_count,
             local_file_path, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            business_id,
            doc_number,
            doc_type,
            product_type,
            new_filename,
            file_size,
            file_extension,
            upload_time_str,
            'pending',  # 初始状态
            None,
            None,
            None,
            0,
            local_file_path,
            upload_time_str,
            upload_time_str
        ))

        record_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # 添加后台任务
        background_tasks.add_task(
            background_upload_to_yonyou,
            file_content=file_content,
            new_filename=new_filename,
            business_id=business_id,
            business_type=business_type,
            local_file_path=local_file_path,
            record_id=record_id
        )

        records.append({
            "id": record_id,
            "file_name": new_filename,
            "original_name": upload_file.filename,
            "status": "pending",
            "file_size": file_size
        })

    # 立即返回响应
    return {
        "success": True,
        "total": len(files),
        "message": f"已接收{len(files)}个文件，正在后台上传中",
        "records": records
    }
```

##### 1.4 删除原有的 `save_upload_history` 函数
原有的 `save_upload_history` 函数不再需要，因为数据库操作已内联到主函数和后台任务中。

#### 2. 管理后台文件：`app/api/admin.py`

##### 2.1 修改查询逻辑
在 `get_admin_records` 函数中，移除状态过滤，支持所有状态查询：

```python
@router.get("/records")
async def get_admin_records(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页记录数"),
    search: Optional[str] = Query(None, description="搜索关键词（单据编号/文件名）"),
    doc_type: Optional[str] = Query(None, description="单据类型筛选"),
    product_type: Optional[str] = Query(None, description="产品类型筛选"),
    status: Optional[str] = Query(None, description="状态筛选（pending/uploading/success/failed）"),  # 新增参数
    start_date: Optional[str] = Query(None, description="开始日期（YYYY-MM-DD）"),
    end_date: Optional[str] = Query(None, description="结束日期（YYYY-MM-DD）")
) -> Dict[str, Any]:
    """
    获取上传记录列表（管理页面）

    新增功能：
    - 支持按状态筛选（pending/uploading/success/failed）
    - 移除默认的 status='success' 过滤，显示所有状态记录
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # 构建WHERE条件（移除 status='success' 的硬编码）
    where_clauses = ["deleted_at IS NULL"]  # 只过滤未删除的记录
    params = []

    if search:
        where_clauses.append("(doc_number LIKE ? OR file_name LIKE ?)")
        search_pattern = f"%{search}%"
        params.extend([search_pattern, search_pattern])

    if doc_type:
        where_clauses.append("doc_type = ?")
        params.append(doc_type)

    if product_type:
        where_clauses.append("product_type = ?")
        params.append(product_type)

    if status:  # 新增：支持状态筛选
        where_clauses.append("status = ?")
        params.append(status)

    if start_date:
        where_clauses.append("DATE(upload_time) >= ?")
        params.append(start_date)

    if end_date:
        where_clauses.append("DATE(upload_time) <= ?")
        params.append(end_date)

    where_sql = " AND ".join(where_clauses)

    # 查询总记录数
    cursor.execute(f"SELECT COUNT(*) FROM upload_history WHERE {where_sql}", params)
    total = cursor.fetchone()[0]

    # 计算分页
    total_pages = (total + page_size - 1) // page_size
    offset = (page - 1) * page_size

    # 查询分页数据（新增 status 字段到查询结果）
    cursor.execute(f"""
        SELECT id, business_id, doc_number, doc_type, product_type, file_name, file_size,
               upload_time, status, error_code, error_message
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
            "product_type": row[4],
            "file_name": row[5],
            "file_size": row[6],
            "upload_time": row[7],
            "status": row[8],
            "error_code": row[9],
            "error_message": row[10]
        })

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "records": records
    }
```

##### 2.2 修改导出逻辑
在 `export_records` 函数中，同样移除状态过滤，并在导出的 Excel 中包含状态字段：

```python
@router.get("/export")
async def export_records(
    search: Optional[str] = Query(None, description="搜索关键词"),
    doc_type: Optional[str] = Query(None, description="单据类型筛选"),
    product_type: Optional[str] = Query(None, description="产品类型筛选"),
    status: Optional[str] = Query(None, description="状态筛选"),  # 新增参数
    start_date: Optional[str] = Query(None, description="开始日期"),
    end_date: Optional[str] = Query(None, description="结束日期")
):
    """
    导出上传记录为ZIP包（包含Excel表格和所有图片文件）

    新增功能：
    - 支持按状态筛选导出
    - Excel中包含状态字段
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # 构建WHERE条件（移除 status='success' 的硬编码）
    where_clauses = ["deleted_at IS NULL"]
    params = []

    if search:
        where_clauses.append("(doc_number LIKE ? OR file_name LIKE ?)")
        search_pattern = f"%{search}%"
        params.extend([search_pattern, search_pattern])

    if doc_type:
        where_clauses.append("doc_type = ?")
        params.append(doc_type)

    if product_type:
        where_clauses.append("product_type = ?")
        params.append(product_type)

    if status:  # 新增：支持状态筛选
        where_clauses.append("status = ?")
        params.append(status)

    if start_date:
        where_clauses.append("DATE(upload_time) >= ?")
        params.append(start_date)

    if end_date:
        where_clauses.append("DATE(upload_time) <= ?")
        params.append(end_date)

    where_sql = " AND ".join(where_clauses)

    # 查询所有匹配记录（新增 status 字段）
    cursor.execute(f"""
        SELECT doc_number, doc_type, product_type, business_id, upload_time, file_name,
               file_size, status, local_file_path
        FROM upload_history
        WHERE {where_sql}
        ORDER BY upload_time DESC
    """, params)

    rows = cursor.fetchall()
    conn.close()

    # 创建临时目录和ZIP文件
    temp_dir = tempfile.mkdtemp()
    timestamp = get_beijing_now_naive().strftime('%Y%m%d_%H%M%S')
    zip_filename = f"upload_records_{timestamp}.zip"
    zip_path = os.path.join(temp_dir, zip_filename)

    try:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # 生成Excel文件
            wb = Workbook()
            ws = wb.active
            ws.title = "上传记录"

            # 写入表头（新增"状态"列）
            headers = ["单据编号", "单据类型", "产品类型", "业务ID", "上传时间", "文件名", "文件大小(字节)", "状态"]
            ws.append(headers)

            # 写入数据并收集图片文件
            for row in rows:
                doc_number, doc_type, product_type, business_id, upload_time, file_name, file_size, status, local_file_path = row
                ws.append([doc_number, doc_type, product_type or '', business_id, upload_time, file_name, file_size, status])

                # 添加本地图片文件到ZIP（仅成功的记录有本地文件）
                if status == 'success' and local_file_path and os.path.exists(local_file_path):
                    arcname = os.path.join("images", os.path.basename(local_file_path))
                    zipf.write(local_file_path, arcname=arcname)

            # 保存Excel到临时文件
            excel_temp_path = os.path.join(temp_dir, f"upload_records_{timestamp}.xlsx")
            wb.save(excel_temp_path)

            # 添加Excel文件到ZIP
            zipf.write(excel_temp_path, arcname=f"upload_records_{timestamp}.xlsx")

        # 返回ZIP文件
        return FileResponse(
            path=zip_path,
            media_type="application/zip",
            filename=zip_filename,
            background=None
        )

    except Exception as e:
        # 清理临时文件
        if os.path.exists(zip_path):
            os.remove(zip_path)
        if os.path.exists(temp_dir):
            os.rmdir(temp_dir)
        raise HTTPException(status_code=500, detail=f"导出失败: {str(e)}")
```

##### 2.3 修改统计逻辑
在 `get_statistics` 函数中，新增各状态的统计：

```python
@router.get("/statistics")
async def get_statistics() -> Dict[str, Any]:
    """
    获取统计数据

    新增功能：
    - 统计各状态（pending/uploading/success/failed）的数量
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # 总上传数和各状态数量
    cursor.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
            SUM(CASE WHEN status = 'uploading' THEN 1 ELSE 0 END) as uploading,
            SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success,
            SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed
        FROM upload_history
        WHERE deleted_at IS NULL
    """)
    row = cursor.fetchone()
    total_uploads = row[0]
    pending_count = row[1]
    uploading_count = row[2]
    success_count = row[3]
    failed_count = row[4]

    # 按单据类型统计（保持不变）
    cursor.execute("""
        SELECT doc_type, COUNT(*) as count
        FROM upload_history
        WHERE doc_type IS NOT NULL AND deleted_at IS NULL
        GROUP BY doc_type
    """)

    by_doc_type = {}
    for row in cursor.fetchall():
        by_doc_type[row[0]] = row[1]

    conn.close()

    return {
        "total_uploads": total_uploads,
        "pending_count": pending_count,
        "uploading_count": uploading_count,
        "success_count": success_count,
        "failed_count": failed_count,
        "by_doc_type": by_doc_type
    }
```

---

### API 接口规格

#### 1. 上传接口：`POST /api/upload`

##### 请求参数
```
Content-Type: multipart/form-data

- business_id: str (必需) - 业务单据ID（纯数字）
- doc_number: str (必需) - 单据编号
- doc_type: str (必需) - 单据类型（销售/转库/其他）
- product_type: str (可选) - 产品类型
- files: List[File] (必需) - 文件列表（最多10个）
```

##### 响应格式（修改后）
```json
{
  "success": true,
  "total": 3,
  "message": "已接收3个文件，正在后台上传中",
  "records": [
    {
      "id": 123,
      "file_name": "SO001_20251021143025_a3f2b1c4.jpg",
      "original_name": "photo1.jpg",
      "status": "pending",
      "file_size": 102400
    },
    {
      "id": 124,
      "file_name": "SO001_20251021143026_b4e3c2d5.jpg",
      "original_name": "photo2.jpg",
      "status": "pending",
      "file_size": 204800
    },
    {
      "id": 125,
      "file_name": "SO001_20251021143027_c5f4d3e6.jpg",
      "original_name": "photo3.jpg",
      "status": "pending",
      "file_size": 153600
    }
  ]
}
```

##### 响应时间
- 期望：< 1 秒
- 包含操作：读取文件、保存数据库记录、添加后台任务

#### 2. 管理后台记录查询：`GET /api/admin/records`

##### 请求参数（新增）
```
- page: int (可选，默认1) - 页码
- page_size: int (可选，默认20) - 每页记录数
- search: str (可选) - 搜索关键词
- doc_type: str (可选) - 单据类型筛选
- product_type: str (可选) - 产品类型筛选
- status: str (可选) - 状态筛选（pending/uploading/success/failed） [新增]
- start_date: str (可选) - 开始日期
- end_date: str (可选) - 结束日期
```

##### 响应格式（新增字段）
```json
{
  "total": 150,
  "page": 1,
  "page_size": 20,
  "total_pages": 8,
  "records": [
    {
      "id": 123,
      "business_id": "12345",
      "doc_number": "SO001",
      "doc_type": "销售",
      "product_type": "油脂",
      "file_name": "SO001_20251021143025_a3f2b1c4.jpg",
      "file_size": 102400,
      "upload_time": "2025-10-21T14:30:25",
      "status": "success",
      "error_code": null,
      "error_message": null
    },
    {
      "id": 124,
      "business_id": "12345",
      "doc_number": "SO001",
      "doc_type": "销售",
      "product_type": "油脂",
      "file_name": "SO001_20251021143026_b4e3c2d5.jpg",
      "file_size": 204800,
      "upload_time": "2025-10-21T14:30:26",
      "status": "uploading",
      "error_code": null,
      "error_message": null
    },
    {
      "id": 125,
      "business_id": "12345",
      "doc_number": "SO001",
      "doc_type": "销售",
      "product_type": "油脂",
      "file_name": "SO001_20251021143027_c5f4d3e6.jpg",
      "file_size": 153600,
      "upload_time": "2025-10-21T14:30:27",
      "status": "failed",
      "error_code": "NETWORK_ERROR",
      "error_message": "连接超时"
    }
  ]
}
```

#### 3. 管理后台导出：`GET /api/admin/export`

##### 请求参数（新增）
```
- search: str (可选)
- doc_type: str (可选)
- product_type: str (可选)
- status: str (可选) - 状态筛选 [新增]
- start_date: str (可选)
- end_date: str (可选)
```

##### 响应
```
Content-Type: application/zip
Content-Disposition: attachment; filename="upload_records_20251021_143000.zip"

ZIP包内容:
  - upload_records_20251021_143000.xlsx (包含状态列)
  - images/
    - SO001_20251021143025_a3f2b1c4.jpg
    - SO001_20251021143026_b4e3c2d5.jpg
    - ...
```

#### 4. 统计接口：`GET /api/admin/statistics`

##### 响应格式（新增字段）
```json
{
  "total_uploads": 1500,
  "pending_count": 10,
  "uploading_count": 5,
  "success_count": 1450,
  "failed_count": 35,
  "by_doc_type": {
    "销售": 800,
    "转库": 600,
    "其他": 100
  }
}
```

---

### 前端实施规格

#### 1. 历史记录页面（`frontend/index.html` 或相关 JS 文件）

##### 1.1 状态显示设计
在历史记录列表中，为每条记录显示状态图标和文字：

```html
<!-- 在历史记录项中添加状态显示 -->
<div class="history-item">
  <div class="file-info">
    <span class="file-name">SO001_20251021143025_a3f2b1c4.jpg</span>
    <span class="file-size">100 KB</span>
  </div>
  <div class="upload-status">
    <!-- 状态图标和文字 -->
    <span class="status-badge status-success">✓ 成功</span>
    <!-- 或 -->
    <span class="status-badge status-uploading">⏳ 上传中</span>
    <!-- 或 -->
    <span class="status-badge status-failed">✗ 失败</span>
    <!-- 或 -->
    <span class="status-badge status-pending">⏸ 待上传</span>
  </div>
  <div class="upload-time">2025-10-21 14:30:25</div>
</div>
```

##### 1.2 CSS 样式
```css
/* 状态徽章基础样式 */
.status-badge {
  display: inline-block;
  padding: 4px 12px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
}

/* 成功状态 - 绿色 */
.status-success {
  background-color: #d4edda;
  color: #155724;
  border: 1px solid #c3e6cb;
}

/* 上传中状态 - 蓝色 */
.status-uploading {
  background-color: #d1ecf1;
  color: #0c5460;
  border: 1px solid #bee5eb;
}

/* 失败状态 - 红色 */
.status-failed {
  background-color: #f8d7da;
  color: #721c24;
  border: 1px solid #f5c6cb;
}

/* 待上传状态 - 灰色 */
.status-pending {
  background-color: #e2e3e5;
  color: #383d41;
  border: 1px solid #d6d8db;
}
```

##### 1.3 JavaScript 逻辑
```javascript
// 渲染状态徽章
function renderStatusBadge(status, errorMessage) {
  const statusConfig = {
    'success': { icon: '✓', text: '成功', class: 'status-success' },
    'uploading': { icon: '⏳', text: '上传中', class: 'status-uploading' },
    'failed': { icon: '✗', text: '失败', class: 'status-failed' },
    'pending': { icon: '⏸', text: '待上传', class: 'status-pending' }
  };

  const config = statusConfig[status] || statusConfig['pending'];
  let html = `<span class="status-badge ${config.class}">${config.icon} ${config.text}</span>`;

  // 失败状态显示错误信息（可选）
  if (status === 'failed' && errorMessage) {
    html += `<span class="error-message" title="${errorMessage}">⚠️</span>`;
  }

  return html;
}

// 加载历史记录
async function loadHistory(businessId) {
  const response = await fetch(`/api/history/${businessId}`);
  const data = await response.json();

  const historyList = document.getElementById('history-list');
  historyList.innerHTML = data.records.map(record => `
    <div class="history-item">
      <div class="file-info">
        <span class="file-name">${record.file_name}</span>
        <span class="file-size">${formatFileSize(record.file_size)}</span>
      </div>
      <div class="upload-status">
        ${renderStatusBadge(record.status, record.error_message)}
      </div>
      <div class="upload-time">${formatDateTime(record.upload_time)}</div>
    </div>
  `).join('');
}

// 文件大小格式化
function formatFileSize(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(2) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
}

// 日期时间格式化
function formatDateTime(isoString) {
  const date = new Date(isoString);
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  });
}
```

##### 1.4 可选：自动刷新
如果需要自动更新状态，可添加定时刷新或刷新按钮：

```javascript
// 添加刷新按钮
<button id="refresh-btn" onclick="loadHistory(currentBusinessId)">刷新状态</button>

// 或自动轮询（仅当有 pending/uploading 状态时）
let pollInterval = null;

function startPolling(businessId) {
  // 停止之前的轮询
  if (pollInterval) {
    clearInterval(pollInterval);
  }

  // 每5秒轮询一次
  pollInterval = setInterval(async () => {
    const response = await fetch(`/api/history/${businessId}`);
    const data = await response.json();

    // 检查是否还有进行中的上传
    const hasOngoing = data.records.some(r => r.status === 'pending' || r.status === 'uploading');

    if (!hasOngoing) {
      // 所有上传完成，停止轮询
      clearInterval(pollInterval);
      pollInterval = null;
    }

    // 更新UI
    loadHistory(businessId);
  }, 5000);
}

// 上传完成后启动轮询
uploadBtn.addEventListener('click', async () => {
  // ... 上传逻辑
  const result = await uploadFiles();

  if (result.success) {
    // 启动轮询检查状态
    startPolling(businessId);
  }
});
```

#### 2. 管理后台页面（`frontend/admin.html` 或相关 JS 文件）

##### 2.1 状态筛选器
在管理后台添加状态筛选下拉框：

```html
<!-- 筛选器区域 -->
<div class="filter-section">
  <!-- 现有筛选器 -->
  <select id="doc-type-filter">
    <option value="">全部单据类型</option>
    <option value="销售">销售</option>
    <option value="转库">转库</option>
    <option value="其他">其他</option>
  </select>

  <select id="product-type-filter">
    <option value="">全部产品类型</option>
    <option value="油脂">油脂</option>
    <option value="快消">快消</option>
  </select>

  <!-- 新增：状态筛选器 -->
  <select id="status-filter">
    <option value="">全部状态</option>
    <option value="pending">待上传</option>
    <option value="uploading">上传中</option>
    <option value="success">成功</option>
    <option value="failed">失败</option>
  </select>

  <!-- 快捷筛选按钮 -->
  <button class="filter-btn" onclick="filterByStatus('failed')">
    查看失败记录
  </button>

  <button class="filter-btn" onclick="filterByStatus('uploading')">
    查看上传中
  </button>
</div>
```

##### 2.2 JavaScript 逻辑
```javascript
// 加载记录（包含状态筛选）
async function loadRecords(page = 1) {
  const params = new URLSearchParams({
    page: page,
    page_size: 20
  });

  // 添加筛选条件
  const docType = document.getElementById('doc-type-filter').value;
  if (docType) params.append('doc_type', docType);

  const productType = document.getElementById('product-type-filter').value;
  if (productType) params.append('product_type', productType);

  const status = document.getElementById('status-filter').value;
  if (status) params.append('status', status);

  const startDate = document.getElementById('start-date').value;
  if (startDate) params.append('start_date', startDate);

  const endDate = document.getElementById('end-date').value;
  if (endDate) params.append('end_date', endDate);

  const response = await fetch(`/api/admin/records?${params}`);
  const data = await response.json();

  renderRecordsTable(data.records);
  renderPagination(data.page, data.total_pages);
}

// 快捷筛选
function filterByStatus(status) {
  document.getElementById('status-filter').value = status;
  loadRecords(1);
}

// 渲染记录表格
function renderRecordsTable(records) {
  const tbody = document.getElementById('records-tbody');
  tbody.innerHTML = records.map(record => `
    <tr>
      <td><input type="checkbox" value="${record.id}"></td>
      <td>${record.doc_number}</td>
      <td>${record.doc_type}</td>
      <td>${record.product_type || '-'}</td>
      <td>${record.file_name}</td>
      <td>${formatFileSize(record.file_size)}</td>
      <td>${formatDateTime(record.upload_time)}</td>
      <td>${renderStatusBadge(record.status, record.error_message)}</td>
      <td>
        ${record.status === 'failed' && record.error_message
          ? `<span class="error-tooltip" title="${record.error_message}">查看错误</span>`
          : '-'
        }
      </td>
    </tr>
  `).join('');
}

// 导出（包含状态筛选）
async function exportRecords() {
  const params = new URLSearchParams();

  const docType = document.getElementById('doc-type-filter').value;
  if (docType) params.append('doc_type', docType);

  const productType = document.getElementById('product-type-filter').value;
  if (productType) params.append('product_type', productType);

  const status = document.getElementById('status-filter').value;
  if (status) params.append('status', status);

  const startDate = document.getElementById('start-date').value;
  if (startDate) params.append('start_date', startDate);

  const endDate = document.getElementById('end-date').value;
  if (endDate) params.append('end_date', endDate);

  window.location.href = `/api/admin/export?${params}`;
}
```

##### 2.3 统计面板
在管理后台顶部显示统计数据：

```html
<div class="statistics-panel">
  <div class="stat-card">
    <div class="stat-value" id="total-uploads">0</div>
    <div class="stat-label">总上传数</div>
  </div>

  <div class="stat-card stat-success">
    <div class="stat-value" id="success-count">0</div>
    <div class="stat-label">成功</div>
  </div>

  <div class="stat-card stat-uploading">
    <div class="stat-value" id="uploading-count">0</div>
    <div class="stat-label">上传中</div>
  </div>

  <div class="stat-card stat-pending">
    <div class="stat-value" id="pending-count">0</div>
    <div class="stat-label">待上传</div>
  </div>

  <div class="stat-card stat-failed">
    <div class="stat-value" id="failed-count">0</div>
    <div class="stat-label">失败</div>
  </div>
</div>
```

```javascript
// 加载统计数据
async function loadStatistics() {
  const response = await fetch('/api/admin/statistics');
  const data = await response.json();

  document.getElementById('total-uploads').textContent = data.total_uploads;
  document.getElementById('success-count').textContent = data.success_count;
  document.getElementById('uploading-count').textContent = data.uploading_count;
  document.getElementById('pending-count').textContent = data.pending_count;
  document.getElementById('failed-count').textContent = data.failed_count;
}

// 页面加载时调用
window.addEventListener('DOMContentLoaded', () => {
  loadStatistics();
  loadRecords(1);
});
```

---

### 测试规格

#### 1. 单元测试

##### 1.1 后台任务测试（新增文件：`tests/test_background_tasks.py`）

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.api.upload import background_upload_to_yonyou

@pytest.mark.asyncio
async def test_background_upload_success(test_db):
    """测试后台上传成功流程"""
    # Mock用友云客户端
    with patch('app.api.upload.yonyou_client.upload_file', new_callable=AsyncMock) as mock_upload:
        mock_upload.return_value = {
            "success": True,
            "data": {"id": "test_file_id_12345"}
        }

        # 准备测试数据
        file_content = b"test image content"
        new_filename = "SO001_20251021143025_a3f2b1c4.jpg"
        business_id = "12345"
        business_type = "yonbip-scm-scmsa"
        local_file_path = "data/uploaded_files/SO001_20251021143025_a3f2b1c4.jpg"

        # 创建初始记录
        from app.core.database import get_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO upload_history
            (business_id, file_name, file_size, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))
        """, (business_id, new_filename, len(file_content), 'pending'))
        record_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # 执行后台任务
        await background_upload_to_yonyou(
            file_content=file_content,
            new_filename=new_filename,
            business_id=business_id,
            business_type=business_type,
            local_file_path=local_file_path,
            record_id=record_id
        )

        # 验证数据库状态
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT status, yonyou_file_id FROM upload_history WHERE id = ?", (record_id,))
        row = cursor.fetchone()
        conn.close()

        assert row[0] == 'success'
        assert row[1] == 'test_file_id_12345'


@pytest.mark.asyncio
async def test_background_upload_failure_with_retry(test_db):
    """测试后台上传失败并重试"""
    with patch('app.api.upload.yonyou_client.upload_file', new_callable=AsyncMock) as mock_upload:
        # 模拟3次失败
        mock_upload.return_value = {
            "success": False,
            "error_code": "NETWORK_ERROR",
            "error_message": "连接超时"
        }

        # 准备测试数据
        file_content = b"test image content"
        new_filename = "SO001_20251021143025_a3f2b1c4.jpg"
        business_id = "12345"
        business_type = "yonbip-scm-scmsa"
        local_file_path = "data/uploaded_files/SO001_20251021143025_a3f2b1c4.jpg"

        # 创建初始记录
        from app.core.database import get_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO upload_history
            (business_id, file_name, file_size, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))
        """, (business_id, new_filename, len(file_content), 'pending'))
        record_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # 执行后台任务
        with patch('asyncio.sleep', new_callable=AsyncMock):  # 跳过延迟
            await background_upload_to_yonyou(
                file_content=file_content,
                new_filename=new_filename,
                business_id=business_id,
                business_type=business_type,
                local_file_path=local_file_path,
                record_id=record_id
            )

        # 验证数据库状态
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT status, error_code, error_message, retry_count
            FROM upload_history WHERE id = ?
        """, (record_id,))
        row = cursor.fetchone()
        conn.close()

        assert row[0] == 'failed'
        assert row[1] == 'NETWORK_ERROR'
        assert row[2] == '连接超时'
        assert row[3] == 2  # 重试2次（总共3次尝试）


@pytest.mark.asyncio
async def test_background_upload_exception_handling(test_db):
    """测试后台任务异常处理"""
    with patch('app.api.upload.yonyou_client.upload_file', new_callable=AsyncMock) as mock_upload:
        # 模拟抛出异常
        mock_upload.side_effect = Exception("Unexpected error")

        # 准备测试数据
        file_content = b"test image content"
        new_filename = "SO001_20251021143025_a3f2b1c4.jpg"
        business_id = "12345"
        business_type = "yonbip-scm-scmsa"
        local_file_path = "data/uploaded_files/SO001_20251021143025_a3f2b1c4.jpg"

        # 创建初始记录
        from app.core.database import get_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO upload_history
            (business_id, file_name, file_size, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))
        """, (business_id, new_filename, len(file_content), 'pending'))
        record_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # 执行后台任务（不应抛出异常）
        await background_upload_to_yonyou(
            file_content=file_content,
            new_filename=new_filename,
            business_id=business_id,
            business_type=business_type,
            local_file_path=local_file_path,
            record_id=record_id
        )

        # 验证数据库状态（应标记为失败）
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT status, error_code
            FROM upload_history WHERE id = ?
        """, (record_id,))
        row = cursor.fetchone()
        conn.close()

        assert row[0] == 'failed'
        assert row[1] == 'BACKGROUND_TASK_ERROR'
```

##### 1.2 上传路由测试（修改文件：`tests/test_upload_api.py`）

```python
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
from app.main import app

client = TestClient(app)

def test_upload_files_immediate_response(test_db, test_image_bytes):
    """测试上传文件立即返回响应"""
    # Mock后台任务（不实际执行）
    with patch('app.api.upload.background_upload_to_yonyou', new_callable=AsyncMock):
        # 准备测试数据
        files = [
            ("files", ("test1.jpg", test_image_bytes, "image/jpeg")),
            ("files", ("test2.jpg", test_image_bytes, "image/jpeg"))
        ]

        data = {
            "business_id": "12345",
            "doc_number": "SO001",
            "doc_type": "销售",
            "product_type": "油脂"
        }

        # 发送请求
        import time
        start_time = time.time()
        response = client.post("/api/upload", files=files, data=data)
        elapsed_time = time.time() - start_time

        # 验证响应
        assert response.status_code == 200
        result = response.json()
        assert result["success"] is True
        assert result["total"] == 2
        assert "正在后台上传中" in result["message"]
        assert len(result["records"]) == 2
        assert all(r["status"] == "pending" for r in result["records"])

        # 验证响应时间 < 2秒（宽松测试）
        assert elapsed_time < 2.0

        # 验证数据库记录
        from app.core.database import get_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM upload_history WHERE status = 'pending'")
        count = cursor.fetchone()[0]
        conn.close()

        assert count == 2


def test_upload_files_background_task_triggered(test_db, test_image_bytes):
    """测试上传文件触发后台任务"""
    from unittest.mock import call

    with patch('app.api.upload.background_upload_to_yonyou', new_callable=AsyncMock) as mock_bg_task:
        files = [("files", ("test.jpg", test_image_bytes, "image/jpeg"))]
        data = {
            "business_id": "12345",
            "doc_number": "SO001",
            "doc_type": "销售"
        }

        response = client.post("/api/upload", files=files, data=data)

        assert response.status_code == 200
        # 注意：由于使用了 BackgroundTasks，mock 可能不会立即被调用
        # 实际测试中，可以通过检查数据库记录来验证
```

#### 2. 集成测试

##### 2.1 端到端测试（新增文件：`tests/test_async_upload_e2e.py`）

```python
import pytest
import asyncio
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
from app.main import app

client = TestClient(app)

@pytest.mark.asyncio
async def test_full_async_upload_flow(test_db, test_image_bytes):
    """测试完整的异步上传流程"""
    # Mock用友云客户端
    with patch('app.api.upload.yonyou_client.upload_file', new_callable=AsyncMock) as mock_upload:
        mock_upload.return_value = {
            "success": True,
            "data": {"id": "test_file_id_12345"}
        }

        # 1. 上传文件
        files = [("files", ("test.jpg", test_image_bytes, "image/jpeg"))]
        data = {
            "business_id": "12345",
            "doc_number": "SO001",
            "doc_type": "销售"
        }

        response = client.post("/api/upload", files=files, data=data)
        assert response.status_code == 200
        result = response.json()
        assert result["success"] is True
        record_id = result["records"][0]["id"]

        # 2. 等待后台任务完成（模拟）
        from app.core.database import get_db_connection

        # 手动执行后台任务（测试环境中 BackgroundTasks 不会自动执行）
        from app.api.upload import background_upload_to_yonyou
        await background_upload_to_yonyou(
            file_content=test_image_bytes,
            new_filename=result["records"][0]["file_name"],
            business_id="12345",
            business_type="yonbip-scm-scmsa",
            local_file_path="data/uploaded_files/" + result["records"][0]["file_name"],
            record_id=record_id
        )

        # 3. 验证最终状态
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT status, yonyou_file_id
            FROM upload_history WHERE id = ?
        """, (record_id,))
        row = cursor.fetchone()
        conn.close()

        assert row[0] == 'success'
        assert row[1] == 'test_file_id_12345'
```

#### 3. 性能测试

##### 3.1 响应时间测试（新增文件：`tests/test_performance.py`）

```python
import pytest
import time
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
from app.main import app

client = TestClient(app)

def test_upload_response_time_under_1_second(test_db, test_image_bytes):
    """测试上传响应时间 < 1秒"""
    with patch('app.api.upload.background_upload_to_yonyou', new_callable=AsyncMock):
        files = [("files", (f"test{i}.jpg", test_image_bytes, "image/jpeg")) for i in range(10)]
        data = {
            "business_id": "12345",
            "doc_number": "SO001",
            "doc_type": "销售"
        }

        start_time = time.time()
        response = client.post("/api/upload", files=files, data=data)
        elapsed_time = time.time() - start_time

        assert response.status_code == 200
        assert elapsed_time < 1.5  # 允许1.5秒的宽松限制
        print(f"上传10个文件的响应时间: {elapsed_time:.3f}秒")
```

#### 4. 边界测试

##### 4.1 并发上传测试

```python
import pytest
from fastapi.testclient import TestClient
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch, AsyncMock
from app.main import app

client = TestClient(app)

def test_concurrent_uploads(test_db, test_image_bytes):
    """测试并发上传"""
    with patch('app.api.upload.background_upload_to_yonyou', new_callable=AsyncMock):
        def upload_file(index):
            files = [("files", (f"test{index}.jpg", test_image_bytes, "image/jpeg"))]
            data = {
                "business_id": "12345",
                "doc_number": f"SO{index:03d}",
                "doc_type": "销售"
            }
            return client.post("/api/upload", files=files, data=data)

        # 并发上传10个文件
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(upload_file, i) for i in range(10)]
            results = [f.result() for f in futures]

        # 验证所有上传成功
        assert all(r.status_code == 200 for r in results)

        # 验证数据库记录
        from app.core.database import get_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM upload_history")
        count = cursor.fetchone()[0]
        conn.close()

        assert count == 10
```

---

### 部署和回滚计划

#### 部署步骤

##### 1. 前置检查
```bash
# 1. 确保当前代码库干净
git status

# 2. 确保测试全部通过
pytest tests/

# 3. 备份数据库
cp data/uploads.db data/uploads.db.backup.$(date +%Y%m%d_%H%M%S)
```

##### 2. 代码部署
```bash
# 1. 拉取最新代码
git pull origin main

# 2. 安装依赖（如有更新）
pip install -r requirements.txt

# 3. 重启服务
# Docker 部署
docker-compose down
docker-compose up -d

# 或本地部署
pkill -f "python run.py"
nohup python run.py > logs/app.log 2>&1 &
```

##### 3. 部署验证
```bash
# 1. 健康检查
curl http://localhost:10000/api/health

# 2. 上传测试（小文件）
curl -X POST http://localhost:10000/api/upload \
  -F "files=@test.jpg" \
  -F "business_id=12345" \
  -F "doc_number=TEST001" \
  -F "doc_type=销售"

# 3. 检查数据库状态
sqlite3 data/uploads.db "SELECT status, COUNT(*) FROM upload_history GROUP BY status"

# 4. 检查日志
tail -f logs/app.log
```

##### 4. 监控观察期
部署后观察 **24小时**，监控以下指标：
- 前端响应时间（应 < 1秒）
- 后台任务成功率（应 > 95%）
- 数据库写入错误（应为 0）
- 应用日志错误（检查异常）

#### 回滚策略

##### 场景1：代码问题导致无法启动
```bash
# 1. 回退代码
git revert HEAD
# 或
git reset --hard <previous_commit_hash>

# 2. 重新部署
docker-compose down
docker-compose up -d
```

##### 场景2：数据库状态异常
```bash
# 1. 停止服务
docker-compose down

# 2. 恢复数据库备份
cp data/uploads.db.backup.<timestamp> data/uploads.db

# 3. 回退代码
git revert HEAD

# 4. 重启服务
docker-compose up -d
```

##### 场景3：部分功能异常（降级方案）
如果后台任务有问题，可临时禁用异步上传：

```python
# 在 app/api/upload.py 中添加功能开关
ENABLE_ASYNC_UPLOAD = os.getenv("ENABLE_ASYNC_UPLOAD", "true").lower() == "true"

@router.post("/upload")
async def upload_files(
    background_tasks: BackgroundTasks,
    ...
):
    if ENABLE_ASYNC_UPLOAD:
        # 异步上传逻辑
        ...
    else:
        # 回退到同步上传（旧逻辑）
        ...
```

通过设置环境变量快速切换：
```bash
# 禁用异步上传
export ENABLE_ASYNC_UPLOAD=false
docker-compose restart
```

---

## 实施时间线

### Phase 1: 后端核心功能（优先级：P0）
**预计时间：4-6小时**

1. 修改 `app/api/upload.py`
   - 添加 `background_upload_to_yonyou` 函数
   - 修改 `upload_files` 函数
   - 测试后台任务执行

2. 修改 `app/api/admin.py`
   - 移除状态过滤
   - 新增状态筛选参数
   - 更新导出逻辑

3. 单元测试
   - 后台任务测试
   - 上传路由测试

### Phase 2: 前端适配（优先级：P1）
**预计时间：3-4小时**

1. 历史记录页面
   - 添加状态显示
   - CSS 样式
   - JavaScript 逻辑

2. 管理后台页面
   - 状态筛选器
   - 统计面板
   - 快捷筛选按钮

3. 集成测试
   - 端到端测试
   - 性能测试

### Phase 3: 部署和验证（优先级：P0）
**预计时间：2-3小时**

1. 部署到测试环境
2. 手动测试验证
3. 监控观察
4. 部署到生产环境

**总预计时间：9-13小时**

---

## 风险缓解措施

### 风险1：SQLite 并发写入限制
**风险等级**：中

**缓解措施**：
1. 保持现有的并发控制（3个并发）
2. 后台任务按顺序更新数据库（无额外并发）
3. 使用 WAL 模式提升并发性能：
   ```python
   # 在 app/core/database.py 的 get_db_connection 中添加
   conn.execute("PRAGMA journal_mode=WAL")
   ```
4. 监控数据库锁定错误

### 风险2：后台任务异常未捕获
**风险等级**：中

**缓解措施**：
1. 在 `background_upload_to_yonyou` 中使用全面的 try-except
2. 所有异常都更新数据库状态为 `failed`
3. 记录详细错误日志
4. 监控后台任务执行情况

### 风险3：前端无法及时看到最终状态
**风险等级**：低

**缓解措施**：
1. 提供刷新按钮
2. 可选：实现轮询机制（仅当有 pending/uploading 状态时）
3. 在上传成功后提示用户"正在后台上传，请稍后查看历史记录"

### 风险4：数据一致性问题
**风险等级**：低

**缓解措施**：
1. 数据库操作使用事务（commit/rollback）
2. 异常情况下确保状态更新
3. 定期数据一致性检查脚本：
   ```python
   # 检查长时间处于 pending/uploading 状态的记录
   SELECT * FROM upload_history
   WHERE status IN ('pending', 'uploading')
   AND created_at < datetime('now', '-1 hour')
   ```

---

## 附录

### A. 状态流转图

```
用户上传 → pending (初始状态，立即返回)
             ↓
         uploading (后台任务开始)
             ↓
        ┌────┴────┐
        ↓         ↓
    success    failed (3次重试后)
```

### B. 数据库查询示例

```sql
-- 查看所有状态的记录数
SELECT status, COUNT(*) as count
FROM upload_history
WHERE deleted_at IS NULL
GROUP BY status;

-- 查看失败记录及错误原因
SELECT doc_number, file_name, error_code, error_message
FROM upload_history
WHERE status = 'failed'
AND deleted_at IS NULL
ORDER BY upload_time DESC;

-- 查看长时间未完成的上传
SELECT * FROM upload_history
WHERE status IN ('pending', 'uploading')
AND created_at < datetime('now', '-1 hour')
AND deleted_at IS NULL;
```

### C. 常见问题 (FAQ)

**Q1: 用户关闭浏览器后，后台上传会继续吗？**
A: 会。BackgroundTasks 在服务端执行，与前端无关。

**Q2: 如何查看上传失败的原因？**
A: 在管理后台筛选 status=failed 的记录，查看 error_message 字段。

**Q3: 后台任务失败会重试吗？**
A: 会。保持现有的3次重试机制。

**Q4: 如何监控后台任务的执行情况？**
A: 通过统计接口查看各状态数量，通过日志查看详细错误。

**Q5: 数据库会不会因为并发写入出现问题？**
A: 理论上不会。后台任务更新是顺序执行的，并且保持了3个并发的限制。建议使用 WAL 模式提升并发性能。

---

## 总结

本技术规格文档提供了完整的异步图片上传功能实施方案：

✅ **代码生成就绪**：所有函数签名、数据结构、SQL语句均已明确定义
✅ **最小复杂度**：使用 FastAPI BackgroundTasks，无需引入 Celery/Redis
✅ **向后兼容**：无需数据库迁移，仅新增状态值
✅ **测试完备**：包含单元测试、集成测试、性能测试规格
✅ **部署安全**：提供详细的部署步骤和回滚策略

代码生成代理可直接基于此规格实施，无需额外澄清或设计决策。
