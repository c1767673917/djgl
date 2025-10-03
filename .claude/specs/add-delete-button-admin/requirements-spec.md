# 技术规格文档 - 后台管理页面删除功能

## 问题陈述

### 业务问题
后台管理页面(`/admin`)缺少删除功能，无法清理错误上传、测试数据或过期记录，导致数据库记录持续累积。

### 当前状态
- 管理页面只有查看、筛选、导出功能
- 没有任何记录删除机制
- 错误数据只能手动操作数据库删除

### 预期结果
- 用户可通过UI界面单条或批量删除记录
- 采用软删除策略，数据库记录标记为已删除但不物理删除
- 本地文件(uploads目录)完整保留
- 删除后的记录在列表中不可见
- 不调用任何用友云API

---

## 解决方案概述

### 实现策略
采用软删除模式，在数据库表中添加`deleted_at`字段标记删除时间，修改所有查询逻辑过滤已删除记录。前端添加删除按钮和批量选择功能，后端提供DELETE API端点处理删除请求。

### 核心变更
1. **数据库变更**: 添加`deleted_at`字段和索引
2. **后端API**: 新增DELETE端点，修改查询逻辑
3. **前端UI**: 添加操作列、复选框、删除按钮
4. **前端逻辑**: 实现删除功能和二次确认

### 成功标准
- 单条删除：点击删除按钮后记录不再显示
- 批量删除：勾选多条记录后一次性删除
- 数据库验证：`deleted_at`字段被正确设置
- 文件验证：uploads目录文件完整保留
- 用户体验：有二次确认，有成功提示，自动刷新列表

---

## 技术实现

### 1. 数据库变更

#### 1.1 表结构修改
在`upload_history`表中添加软删除字段：

```sql
-- 添加删除时间字段
ALTER TABLE upload_history ADD COLUMN deleted_at TEXT DEFAULT NULL;

-- 创建索引优化查询性能
CREATE INDEX IF NOT EXISTS idx_deleted_at ON upload_history(deleted_at);
```

#### 1.2 数据库初始化更新
**文件**: `/Users/lichuansong/Desktop/projects/单据上传管理/app/core/database.py`

在`init_database()`函数中添加字段检查和索引创建：

```python
# 在第45-56行的字段检查部分后添加
if 'deleted_at' not in columns:
    cursor.execute("ALTER TABLE upload_history ADD COLUMN deleted_at TEXT DEFAULT NULL")

# 在第82-87行的索引创建部分后添加
cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_deleted_at
    ON upload_history(deleted_at)
""")
```

**修改位置**:
- 第45-56行：字段检查逻辑
- 第82-87行：索引创建逻辑

---

### 2. 后端API实现

#### 2.1 新增DELETE端点
**文件**: `/Users/lichuansong/Desktop/projects/单据上传管理/app/api/admin.py`

在文件末尾(第276行后)添加新的DELETE端点：

```python
from pydantic import BaseModel


class DeleteRecordsRequest(BaseModel):
    """删除记录请求模型"""
    ids: List[int]


@router.delete("/records")
async def delete_records(request: DeleteRecordsRequest) -> Dict[str, Any]:
    """
    软删除上传记录（批量）

    请求体:
    {
        "ids": [1, 2, 3]  // 要删除的记录ID列表
    }

    响应格式:
    {
        "success": true,
        "deleted_count": 3,
        "message": "成功删除3条记录"
    }

    说明:
    - 采用软删除策略，只标记deleted_at字段，不物理删除数据
    - 不删除本地文件系统的文件
    - 幂等性设计：重复删除已删除的记录不报错
    - 不调用用友云API
    """
    if not request.ids:
        raise HTTPException(status_code=400, detail="请至少选择一条记录")

    # 验证所有ID为正整数
    if any(id <= 0 for id in request.ids):
        raise HTTPException(status_code=400, detail="无效的记录ID")

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # 构建IN子句的占位符
        placeholders = ','.join('?' * len(request.ids))

        # 软删除：设置deleted_at字段为当前时间
        current_time = datetime.now().isoformat()
        cursor.execute(f"""
            UPDATE upload_history
            SET deleted_at = ?
            WHERE id IN ({placeholders})
            AND deleted_at IS NULL
        """, [current_time] + request.ids)

        deleted_count = cursor.rowcount
        conn.commit()

        return {
            "success": True,
            "deleted_count": deleted_count,
            "message": f"成功删除{deleted_count}条记录"
        }

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")

    finally:
        conn.close()
```

**依赖导入**: 在文件顶部(第1-13行)确保已导入`pydantic.BaseModel`

#### 2.2 修改现有查询逻辑
**文件**: `/Users/lichuansong/Desktop/projects/单据上传管理/app/api/admin.py`

所有涉及`upload_history`表查询的地方都需要添加`deleted_at IS NULL`条件：

**修改1**: `get_admin_records()`函数 - 第48-72行
```python
# 原第52行: where_clauses = ["status = 'success'"]
# 修改为:
where_clauses = ["status = 'success'", "deleted_at IS NULL"]
```

**修改2**: `export_records()`函数 - 第133-158行
```python
# 原第137行: where_clauses = ["status = 'success'"]
# 修改为:
where_clauses = ["status = 'success'", "deleted_at IS NULL"]
```

**修改3**: `get_statistics()`函数 - 第244-250行
```python
# 原SQL查询(第244-250行):
cursor.execute("""
    SELECT
        COUNT(*) as total,
        SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success,
        SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed
    FROM upload_history
""")

# 修改为:
cursor.execute("""
    SELECT
        COUNT(*) as total,
        SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success,
        SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed
    FROM upload_history
    WHERE deleted_at IS NULL
""")
```

**修改4**: `get_statistics()`函数 - 第257-263行
```python
# 原SQL查询(第257-263行):
cursor.execute("""
    SELECT doc_type, COUNT(*) as count
    FROM upload_history
    WHERE doc_type IS NOT NULL
    GROUP BY doc_type
""")

# 修改为:
cursor.execute("""
    SELECT doc_type, COUNT(*) as count
    FROM upload_history
    WHERE doc_type IS NOT NULL AND deleted_at IS NULL
    GROUP BY doc_type
""")
```

---

### 3. 前端UI实现

#### 3.1 HTML结构变更
**文件**: `/Users/lichuansong/Desktop/projects/单据上传管理/app/static/admin.html`

**变更1**: 添加批量删除按钮(第17行后)
```html
<!-- 在第17行的btnExport按钮后添加 -->
<button class="btn-delete" id="btnBatchDelete" style="display: none;">批量删除</button>
```

**变更2**: 修改表格头部(第75-84行)
```html
<!-- 原表头 -->
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

<!-- 修改为 -->
<thead>
    <tr>
        <th width="40">
            <input type="checkbox" id="selectAll" title="全选">
        </th>
        <th>单据编号</th>
        <th>单据类型</th>
        <th>业务ID</th>
        <th>上传时间</th>
        <th>文件名</th>
        <th>大小</th>
        <th>状态</th>
        <th width="80">操作</th>
    </tr>
</thead>
```

#### 3.2 CSS样式添加
**文件**: `/Users/lichuansong/Desktop/projects/单据上传管理/app/static/css/admin.css`

在文件末尾添加新样式：

```css
/* 删除按钮样式 */
.btn-delete {
    background-color: #e74c3c;
    color: white;
    border: none;
    padding: 10px 20px;
    border-radius: 4px;
    cursor: pointer;
    font-size: 14px;
    transition: background-color 0.3s;
}

.btn-delete:hover {
    background-color: #c0392b;
}

.btn-delete:disabled {
    background-color: #cccccc;
    cursor: not-allowed;
}

/* 单行删除按钮 */
.btn-delete-row {
    background-color: #e74c3c;
    color: white;
    border: none;
    padding: 4px 10px;
    border-radius: 3px;
    cursor: pointer;
    font-size: 12px;
    transition: background-color 0.2s;
}

.btn-delete-row:hover {
    background-color: #c0392b;
}

/* 复选框样式 */
.row-checkbox {
    width: 16px;
    height: 16px;
    cursor: pointer;
}

#selectAll {
    width: 16px;
    height: 16px;
    cursor: pointer;
}

/* 操作列居中 */
.data-table td:last-child {
    text-align: center;
}
```

---

### 4. 前端逻辑实现

#### 4.1 全局状态扩展
**文件**: `/Users/lichuansong/Desktop/projects/单据上传管理/app/static/js/admin.js`

在第1-13行的state对象中添加选中记录跟踪：

```javascript
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
    },
    selectedIds: new Set()  // 新增：跟踪选中的记录ID
};
```

#### 4.2 DOM元素扩展
在第16-50行的elements对象中添加新元素引用：

```javascript
const elements = {
    // ... 现有元素 ...

    // 删除相关 (在btnExport后添加)
    btnBatchDelete: document.getElementById('btnBatchDelete'),
    selectAll: document.getElementById('selectAll'),

    // ... 其他元素 ...
};
```

#### 4.3 事件绑定扩展
在第53-73行的init()函数中添加新的事件监听：

```javascript
function init() {
    // ... 现有事件绑定 ...

    // 删除相关事件
    elements.btnBatchDelete.addEventListener('click', handleBatchDelete);
    elements.selectAll.addEventListener('change', handleSelectAll);

    // ... 其他初始化代码 ...
}
```

#### 4.4 新增核心函数
在文件末尾(第260行后)添加以下函数：

```javascript
// 处理全选/取消全选
function handleSelectAll() {
    const checkboxes = document.querySelectorAll('.row-checkbox');
    const isChecked = elements.selectAll.checked;

    checkboxes.forEach(checkbox => {
        checkbox.checked = isChecked;
        const recordId = parseInt(checkbox.dataset.id);

        if (isChecked) {
            state.selectedIds.add(recordId);
        } else {
            state.selectedIds.delete(recordId);
        }
    });

    updateBatchDeleteButton();
}

// 处理单行复选框变化
function handleCheckboxChange(event) {
    const recordId = parseInt(event.target.dataset.id);

    if (event.target.checked) {
        state.selectedIds.add(recordId);
    } else {
        state.selectedIds.delete(recordId);
    }

    // 更新全选框状态
    const checkboxes = document.querySelectorAll('.row-checkbox');
    const checkedCount = document.querySelectorAll('.row-checkbox:checked').length;
    elements.selectAll.checked = checkedCount === checkboxes.length;
    elements.selectAll.indeterminate = checkedCount > 0 && checkedCount < checkboxes.length;

    updateBatchDeleteButton();
}

// 更新批量删除按钮显示状态
function updateBatchDeleteButton() {
    if (state.selectedIds.size > 0) {
        elements.btnBatchDelete.style.display = 'inline-block';
        elements.btnBatchDelete.textContent = `批量删除 (${state.selectedIds.size})`;
    } else {
        elements.btnBatchDelete.style.display = 'none';
    }
}

// 处理批量删除
async function handleBatchDelete() {
    if (state.selectedIds.size === 0) {
        showToast('请至少选择一条记录', 'error');
        return;
    }

    const confirmMessage = `确定要删除选中的 ${state.selectedIds.size} 条记录吗？\n\n注意：这将标记记录为已删除，但不会删除本地文件。`;

    if (!confirm(confirmMessage)) {
        return;
    }

    try {
        const response = await fetch('/api/admin/records', {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                ids: Array.from(state.selectedIds)
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || '删除失败');
        }

        const result = await response.json();
        showToast(result.message, 'success');

        // 清空选中状态
        state.selectedIds.clear();
        elements.selectAll.checked = false;
        updateBatchDeleteButton();

        // 刷新列表和统计
        await Promise.all([loadRecords(), loadStatistics()]);

    } catch (error) {
        showToast('删除失败: ' + error.message, 'error');
    }
}

// 处理单行删除
async function handleDeleteRow(recordId) {
    const confirmMessage = '确定要删除这条记录吗？\n\n注意：这将标记记录为已删除，但不会删除本地文件。';

    if (!confirm(confirmMessage)) {
        return;
    }

    try {
        const response = await fetch('/api/admin/records', {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                ids: [recordId]
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || '删除失败');
        }

        const result = await response.json();
        showToast(result.message, 'success');

        // 从选中集合中移除（如果存在）
        state.selectedIds.delete(recordId);
        updateBatchDeleteButton();

        // 刷新列表和统计
        await Promise.all([loadRecords(), loadStatistics()]);

    } catch (error) {
        showToast('删除失败: ' + error.message, 'error');
    }
}
```

#### 4.5 修改renderTable函数
修改第136-154行的renderTable函数，添加复选框和删除按钮：

```javascript
// 原函数
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

// 修改为
function renderTable(records) {
    elements.tableBody.innerHTML = records.map(record => `
        <tr>
            <td>
                <input
                    type="checkbox"
                    class="row-checkbox"
                    data-id="${record.id}"
                    ${state.selectedIds.has(record.id) ? 'checked' : ''}
                >
            </td>
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
            <td>
                <button class="btn-delete-row" data-id="${record.id}">删除</button>
            </td>
        </tr>
    `).join('');

    // 绑定复选框事件
    document.querySelectorAll('.row-checkbox').forEach(checkbox => {
        checkbox.addEventListener('change', handleCheckboxChange);
    });

    // 绑定删除按钮事件
    document.querySelectorAll('.btn-delete-row').forEach(button => {
        button.addEventListener('click', (e) => {
            const recordId = parseInt(e.target.dataset.id);
            handleDeleteRow(recordId);
        });
    });

    // 更新批量删除按钮状态
    updateBatchDeleteButton();
}
```

---

## 实现顺序

### Phase 1: 数据库迁移
1. 修改 `/Users/lichuansong/Desktop/projects/单据上传管理/app/core/database.py`
   - 添加`deleted_at`字段检查和创建逻辑
   - 添加索引创建逻辑
2. 重启应用触发数据库初始化

**验证**: 使用SQLite客户端检查`upload_history`表是否包含`deleted_at`字段和索引

### Phase 2: 后端API实现
1. 修改 `/Users/lichuansong/Desktop/projects/单据上传管理/app/api/admin.py`
   - 添加`DeleteRecordsRequest`模型
   - 添加`delete_records()`端点
   - 修改所有查询添加`deleted_at IS NULL`条件
2. 测试DELETE端点功能

**验证**: 使用Postman或curl测试DELETE /api/admin/records端点

### Phase 3: 前端UI变更
1. 修改 `/Users/lichuansong/Desktop/projects/单据上传管理/app/static/admin.html`
   - 添加批量删除按钮
   - 修改表格头部添加全选复选框和操作列
2. 修改 `/Users/lichuansong/Desktop/projects/单据上传管理/app/static/css/admin.css`
   - 添加删除按钮样式

**验证**: 浏览器检查页面布局是否正确

### Phase 4: 前端逻辑实现
1. 修改 `/Users/lichuansong/Desktop/projects/单据上传管理/app/static/js/admin.js`
   - 扩展全局状态和DOM元素
   - 添加删除相关函数
   - 修改renderTable函数
   - 绑定事件监听器

**验证**: 浏览器测试单条删除和批量删除功能

---

## 验证计划

### 单元测试场景

#### 后端测试
**测试文件**: 创建 `tests/test_admin_delete.py`（可选）

```python
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_delete_single_record():
    """测试单条记录删除"""
    response = client.delete("/api/admin/records", json={"ids": [1]})
    assert response.status_code == 200
    assert response.json()["success"] == True
    assert response.json()["deleted_count"] >= 0

def test_delete_batch_records():
    """测试批量删除"""
    response = client.delete("/api/admin/records", json={"ids": [1, 2, 3]})
    assert response.status_code == 200
    assert response.json()["success"] == True

def test_delete_empty_ids():
    """测试空ID列表"""
    response = client.delete("/api/admin/records", json={"ids": []})
    assert response.status_code == 400
    assert "至少选择一条记录" in response.json()["detail"]

def test_delete_invalid_ids():
    """测试无效ID"""
    response = client.delete("/api/admin/records", json={"ids": [-1, 0]})
    assert response.status_code == 400
    assert "无效的记录ID" in response.json()["detail"]

def test_query_excludes_deleted():
    """测试查询排除已删除记录"""
    # 删除记录
    client.delete("/api/admin/records", json={"ids": [1]})

    # 查询记录
    response = client.get("/api/admin/records?page=1&page_size=20")
    records = response.json()["records"]

    # 验证已删除记录不在结果中
    assert not any(r["id"] == 1 for r in records)
```

#### 前端测试
**手动测试检查清单**:

1. **单条删除测试**
   - [ ] 点击删除按钮，弹出确认对话框
   - [ ] 确认后记录从列表中消失
   - [ ] 显示成功提示消息
   - [ ] 列表自动刷新
   - [ ] 统计数据更新

2. **批量删除测试**
   - [ ] 勾选多条记录，批量删除按钮显示
   - [ ] 批量删除按钮显示选中数量
   - [ ] 点击批量删除，弹出确认对话框
   - [ ] 确认后所有选中记录消失
   - [ ] 选中状态清空，批量删除按钮隐藏

3. **全选/取消全选测试**
   - [ ] 点击全选复选框，所有记录被选中
   - [ ] 再次点击，所有记录取消选中
   - [ ] 手动选中部分记录，全选框显示不确定状态

4. **边界情况测试**
   - [ ] 未选中任何记录，批量删除按钮隐藏
   - [ ] 取消确认对话框，记录保持不变
   - [ ] 删除后翻页，选中状态保持正确

### 集成测试场景

#### 测试场景1: 完整删除流程
```
1. 打开管理页面
2. 筛选条件: 单据类型=销售
3. 勾选前3条记录
4. 点击批量删除
5. 确认对话框选择"确定"
6. 验证:
   - 显示"成功删除3条记录"提示
   - 3条记录从列表消失
   - 统计数据中总数减少3
   - uploads目录文件仍然存在
```

#### 测试场景2: 软删除验证
```
1. 使用SQLite客户端连接数据库
2. 执行: SELECT id, deleted_at FROM upload_history WHERE id IN (1,2,3)
3. 验证:
   - deleted_at字段不为NULL
   - deleted_at时间戳接近当前时间
   - 记录仍存在于数据库中
```

#### 测试场景3: 查询过滤验证
```
1. 删除部分记录
2. 刷新管理页面
3. 验证:
   - 已删除记录不在列表中显示
   - 分页导航正确
   - 导出功能不包含已删除记录
   - 统计数据不包含已删除记录
```

#### 测试场景4: 并发删除测试
```
1. 打开两个浏览器窗口
2. 窗口A: 勾选记录ID=1
3. 窗口B: 勾选记录ID=1
4. 窗口A: 点击删除并确认
5. 窗口B: 点击删除并确认
6. 验证:
   - 两次删除都显示成功
   - 记录只被标记删除一次
   - deleted_at字段值以最后操作为准
```

### 业务逻辑验证

#### 验证点1: 本地文件保留
```bash
# 删除前检查文件
ls -la uploads/

# 执行删除操作
# (通过UI删除记录)

# 删除后再次检查
ls -la uploads/

# 验证: 文件数量和内容完全一致
```

#### 验证点2: 用友系统隔离
```python
# 在delete_records()函数中添加日志
import logging
logger = logging.getLogger(__name__)

@router.delete("/records")
async def delete_records(request: DeleteRecordsRequest):
    logger.info(f"Deleting records: {request.ids}")
    # ... 删除逻辑 ...
    logger.info("No YonYou API calls made")

# 验证: 日志中无任何用友API调用
```

#### 验证点3: 幂等性验证
```
1. 删除记录ID=1
2. 再次删除记录ID=1
3. 验证:
   - 两次操作都返回success=true
   - deleted_count第二次为0
   - deleted_at字段值不变（第一次删除的时间）
```

---

## 集成要点

### 与现有代码的集成方式

#### 1. 数据库集成
- **集成点**: `app/core/database.py:init_database()`
- **集成方式**: 在现有字段检查逻辑中添加`deleted_at`检查
- **注意事项**: 使用`IF NOT EXISTS`避免重复创建索引

#### 2. API集成
- **集成点**: `app/api/admin.py`
- **集成方式**:
  - 在路由器中添加新端点
  - 修改现有查询的WHERE子句
- **注意事项**: 保持响应格式与现有端点一致

#### 3. 前端集成
- **集成点**: `app/static/admin.html`和`app/static/js/admin.js`
- **集成方式**:
  - 扩展现有表格结构
  - 复用现有的Toast提示机制
  - 复用现有的fetch封装模式
- **注意事项**: 不破坏现有分页和筛选功能

### 需要修改的现有函数

| 文件 | 函数名 | 修改内容 | 位置 |
|------|--------|----------|------|
| `app/core/database.py` | `init_database()` | 添加deleted_at字段检查和索引创建 | 第45-87行 |
| `app/api/admin.py` | `get_admin_records()` | WHERE子句添加`deleted_at IS NULL` | 第52行 |
| `app/api/admin.py` | `export_records()` | WHERE子句添加`deleted_at IS NULL` | 第137行 |
| `app/api/admin.py` | `get_statistics()` | 两处SQL添加`deleted_at IS NULL` | 第244,257行 |
| `app/static/js/admin.js` | `renderTable()` | 添加复选框和删除按钮 | 第136-154行 |
| `app/static/js/admin.js` | `init()` | 添加删除相关事件绑定 | 第53-73行 |

### 代码复用建议

#### 1. 复用Toast提示机制
```javascript
// 现有的showToast函数(第248-256行)无需修改
// 直接在删除成功/失败时调用
showToast('成功删除3条记录', 'success');
showToast('删除失败: ' + error.message, 'error');
```

#### 2. 复用fetch模式
```javascript
// 参考现有的loadRecords()函数(第91-134行)的fetch调用方式
const response = await fetch('/api/admin/records', {
    method: 'DELETE',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ids: selectedIds})
});
```

#### 3. 复用数据库连接模式
```python
# 参考现有端点的数据库操作模式
conn = get_db_connection()
cursor = conn.cursor()
try:
    # 执行SQL
    conn.commit()
except Exception as e:
    conn.rollback()
    raise
finally:
    conn.close()
```

#### 4. 复用错误处理模式
```python
# 参考现有端点的HTTPException使用方式
if not request.ids:
    raise HTTPException(status_code=400, detail="请至少选择一条记录")
```

---

## 测试计划

### 开发环境测试

#### 步骤1: 数据库迁移测试
```bash
# 1. 备份现有数据库
cp data/upload_history.db data/upload_history.db.backup

# 2. 启动应用触发数据库初始化
python -m uvicorn app.main:app --reload

# 3. 验证字段和索引
sqlite3 data/upload_history.db
> PRAGMA table_info(upload_history);
> SELECT name FROM sqlite_master WHERE type='index';
> .exit

# 预期结果: 显示deleted_at字段和idx_deleted_at索引
```

#### 步骤2: API端点测试
```bash
# 使用curl测试DELETE端点

# 测试1: 正常删除
curl -X DELETE http://localhost:8000/api/admin/records \
  -H "Content-Type: application/json" \
  -d '{"ids": [1, 2]}'

# 预期响应:
# {"success": true, "deleted_count": 2, "message": "成功删除2条记录"}

# 测试2: 空ID列表
curl -X DELETE http://localhost:8000/api/admin/records \
  -H "Content-Type: application/json" \
  -d '{"ids": []}'

# 预期响应:
# {"detail": "请至少选择一条记录"}

# 测试3: 验证查询过滤
curl http://localhost:8000/api/admin/records?page=1

# 预期响应: records数组中不包含ID为1和2的记录
```

#### 步骤3: 前端功能测试
```
1. 打开浏览器访问 http://localhost:8000/admin
2. 打开浏览器开发者工具(F12)
3. 执行以下测试:

测试用例1: 单条删除
- 点击任意记录的删除按钮
- 检查Console: 无JavaScript错误
- 检查Network: DELETE请求返回200
- 验证: 记录从列表消失

测试用例2: 批量删除
- 勾选3条记录
- 点击批量删除按钮
- 检查Console和Network
- 验证: 3条记录全部消失

测试用例3: 全选功能
- 点击表头全选框
- 验证: 当前页所有记录被选中
- 点击批量删除
- 验证: 当前页所有记录消失

测试用例4: 取消确认
- 点击删除按钮
- 在确认对话框点击"取消"
- 验证: 记录保持不变
```

### 生产环境测试计划

#### 冒烟测试(Smoke Test)
```
1. 部署后立即执行:
   - 访问管理页面，检查页面加载正常
   - 检查表格是否正确显示(包含新的复选框和操作列)
   - 点击一个删除按钮，验证确认对话框出现
   - 取消操作，验证无影响

2. 回归测试:
   - 执行现有功能: 筛选、分页、导出
   - 验证: 所有现有功能正常工作
```

#### 性能测试
```
测试场景: 批量删除100条记录
- 预期响应时间: <2秒
- 监控数据库锁定时间
- 检查UI无卡顿现象
```

---

## 附录

### 完整文件修改清单

| 文件路径 | 修改类型 | 行数变化 | 优先级 |
|----------|----------|----------|--------|
| `/Users/lichuansong/Desktop/projects/单据上传管理/app/core/database.py` | 修改 | +8行 | P0 |
| `/Users/lichuansong/Desktop/projects/单据上传管理/app/api/admin.py` | 新增+修改 | +60行 | P0 |
| `/Users/lichuansong/Desktop/projects/单据上传管理/app/static/admin.html` | 修改 | +11行 | P1 |
| `/Users/lichuansong/Desktop/projects/单据上传管理/app/static/css/admin.css` | 新增 | +50行 | P1 |
| `/Users/lichuansong/Desktop/projects/单据上传管理/app/static/js/admin.js` | 新增+修改 | +120行 | P1 |

### 数据库Schema对比

#### 修改前
```sql
CREATE TABLE upload_history (
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
    local_file_path VARCHAR(500),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

#### 修改后
```sql
CREATE TABLE upload_history (
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
    local_file_path VARCHAR(500),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT DEFAULT NULL  -- 新增字段
);

-- 新增索引
CREATE INDEX idx_deleted_at ON upload_history(deleted_at);
```

### API接口文档

#### DELETE /api/admin/records

**描述**: 软删除上传记录（批量）

**请求方法**: DELETE

**请求头**:
```
Content-Type: application/json
```

**请求体**:
```json
{
    "ids": [1, 2, 3]
}
```

**请求体参数**:
| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| ids | array[int] | 是 | 要删除的记录ID列表，至少包含1个正整数 |

**成功响应** (200 OK):
```json
{
    "success": true,
    "deleted_count": 3,
    "message": "成功删除3条记录"
}
```

**错误响应**:

400 Bad Request - 参数错误:
```json
{
    "detail": "请至少选择一条记录"
}
```

400 Bad Request - ID无效:
```json
{
    "detail": "无效的记录ID"
}
```

500 Internal Server Error - 服务器错误:
```json
{
    "detail": "删除失败: [错误信息]"
}
```

**幂等性**: 是（重复删除已删除的记录不会报错）

**副作用**:
- 数据库记录的`deleted_at`字段被设置为当前时间
- 本地文件系统不受影响
- 不调用任何外部API

### 前端组件说明

#### 批量删除按钮
```html
<button class="btn-delete" id="btnBatchDelete" style="display: none;">
    批量删除
</button>
```

**显示逻辑**:
- 默认隐藏
- 当`state.selectedIds.size > 0`时显示
- 按钮文本动态显示选中数量，如"批量删除 (3)"

#### 全选复选框
```html
<input type="checkbox" id="selectAll" title="全选">
```

**状态**:
- `checked`: 所有记录都被选中
- `unchecked`: 没有记录被选中
- `indeterminate`: 部分记录被选中

#### 单行删除按钮
```html
<button class="btn-delete-row" data-id="123">删除</button>
```

**事件**: 点击触发`handleDeleteRow(recordId)`函数

### 错误处理矩阵

| 错误场景 | 前端处理 | 后端处理 | 用户提示 |
|----------|----------|----------|----------|
| 未选中记录 | 检查selectedIds.size | 检查ids数组长度 | "请至少选择一条记录" |
| 网络请求失败 | try-catch捕获 | - | "删除失败: [错误信息]" |
| 后端返回400 | 解析error.detail | 抛出HTTPException | error.detail内容 |
| 后端返回500 | 解析error.detail | 数据库rollback | "删除失败: [错误信息]" |
| ID不存在 | - | 幂等性处理,返回deleted_count=0 | "成功删除0条记录" |
| 并发删除 | - | WHERE deleted_at IS NULL | 后删除的操作deleted_count=0 |

---

## 风险评估

### 潜在风险

#### 风险1: 数据迁移失败
**概率**: 低
**影响**: 高
**缓解措施**:
- 使用`ALTER TABLE ADD COLUMN IF NOT EXISTS`语法
- 在init_database()中检查字段是否存在
- 部署前在开发环境完整测试

#### 风险2: 性能影响
**概率**: 中
**影响**: 中
**缓解措施**:
- 在deleted_at字段上创建索引
- 批量删除限制最大100条（前端无限制，后端可考虑添加）

#### 风险3: 误删除
**概率**: 中
**影响**: 低（因为是软删除）
**缓解措施**:
- 二次确认对话框
- 软删除策略，数据可恢复
- 本地文件保留

#### 风险4: 前端兼容性
**概率**: 低
**影响**: 中
**缓解措施**:
- 使用标准HTML5复选框
- CSS样式兼容主流浏览器
- JavaScript使用ES6+但不涉及最新特性

### 回滚计划

#### 场景1: 数据库迁移失败
```sql
-- 回滚SQL
ALTER TABLE upload_history DROP COLUMN deleted_at;
DROP INDEX IF EXISTS idx_deleted_at;
```

#### 场景2: 功能异常需要回滚
1. 恢复备份的数据库文件
2. 回滚代码到上一个commit
3. 重启应用

```bash
# 恢复数据库
cp data/upload_history.db.backup data/upload_history.db

# 回滚Git
git revert <commit-hash>

# 重启应用
systemctl restart upload-manager
```

---

## 实施检查清单

### 开发阶段
- [ ] 阅读完整技术规格文档
- [ ] 备份现有数据库
- [ ] 修改`app/core/database.py`添加字段和索引
- [ ] 修改`app/api/admin.py`实现DELETE端点
- [ ] 修改`app/api/admin.py`所有查询添加deleted_at过滤
- [ ] 修改`app/static/admin.html`添加UI元素
- [ ] 创建或修改`app/static/css/admin.css`添加样式
- [ ] 修改`app/static/js/admin.js`实现删除逻辑
- [ ] 本地测试数据库迁移
- [ ] 本地测试DELETE API端点
- [ ] 本地测试前端删除功能

### 测试阶段
- [ ] 单元测试: DELETE API端点
- [ ] 集成测试: 完整删除流程
- [ ] 边界测试: 空选择、重复删除、并发删除
- [ ] 性能测试: 批量删除100条记录
- [ ] 兼容性测试: Chrome, Firefox, Safari
- [ ] 回归测试: 现有功能(筛选、分页、导出)

### 部署阶段
- [ ] 备份生产数据库
- [ ] 部署代码到生产环境
- [ ] 验证数据库迁移成功
- [ ] 冒烟测试: 访问管理页面
- [ ] 执行一次测试删除操作
- [ ] 验证统计数据正确
- [ ] 监控服务器日志无异常

### 上线验证
- [ ] 功能可用性: 删除按钮正常工作
- [ ] 数据一致性: 已删除记录不显示
- [ ] 文件完整性: uploads目录文件保留
- [ ] 性能正常: 响应时间<2秒
- [ ] 无错误日志: 检查应用日志

---

**文档版本**: 1.0
**创建时间**: 2025-10-03
**文档状态**: ✅ 实现就绪
**预计工作量**: 1.5-2小时
**复杂度评级**: 中等
**风险等级**: 低
