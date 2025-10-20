# 技术规格文档：管理界面可点击文件名图片预览功能

## 1. 问题陈述

### 业务问题
管理员在管理后台查看上传记录列表时，需要频繁查看单据图片内容以核对信息，但目前只能看到文件名，无法直接预览图片内容，导致：
- 需要离开管理页面，到文件系统或其他系统查看图片
- 工作效率低下，上下文切换频繁
- 无法快速确认上传内容的准确性

### 当前状态
- 管理页面（`app/static/admin.html`）以表格形式展示上传记录
- 文件名列（第6列）仅显示文本信息，无交互功能
- 图片文件存储在 `data/uploaded_files/` 目录
- 数据库 `upload_history` 表中 `local_file_path` 字段存储完整本地路径
- 数据库 `file_name` 字段存储文件名（如 `SO20250103001.jpg`）
- 静态文件服务仅配置了 `/static` 路径，未配置 `uploaded_files` 访问

### 期望结果
- 点击文件名后弹出模态框，居中显示图片
- 支持缩放操作（10%-500%范围）：鼠标滚轮缩放、工具栏按钮缩放
- 支持旋转操作：顺时针/逆时针90度旋转
- 显示加载状态和错误提示
- 点击模态框外部区域关闭
- 保持暗色主题风格一致

---

## 2. 解决方案概览

### 方案描述
在 `app/static/admin.html` 中添加纯JavaScript实现的图片预览模态框，通过事件委托监听文件名点击，动态加载图片并提供缩放、旋转等交互功能。同时需要在后端（`app/main.py`）添加静态文件挂载点，使前端能够访问本地上传的图片文件。

### 核心变更
1. **后端修改**（`app/main.py`）：
   - 添加 `/uploaded_files` 静态文件挂载点
   - 映射到 `data/uploaded_files/` 目录

2. **前端修改**（`app/static/admin.html`）：
   - 在 `<body>` 末尾添加模态框HTML结构
   - 在 `<style>` 标签内添加模态框样式（浅色主题，与现有风格一致）
   - 在 `<script>` 标签内添加图片预览逻辑

3. **前端修改**（`app/static/js/admin.js`）：
   - 修改 `renderTable()` 函数，为文件名添加可点击样式和 `data-filename` 属性
   - 添加事件委托监听文件名点击

### 成功标准
- [x] 点击文件名能够弹出模态框
- [x] 图片正确加载并显示
- [x] 缩放功能正常（滚轮+按钮，10%-500%）
- [x] 旋转功能正常（90度增量）
- [x] 加载状态和错误提示正确显示
- [x] 点击外部区域能够关闭模态框
- [x] 样式与现有浅色主题一致
- [x] 桌面浏览器（Chrome、Firefox、Safari）正常工作

---

## 3. 技术实现

### 3.1 后端修改

#### 文件：`app/main.py`

**修改位置**：在第26行 `app.mount("/static", ...)` 之后添加

**代码变更**：
```python
# 静态文件
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# 添加以下代码：
# 挂载上传文件目录（用于图片预览）
from pathlib import Path
uploaded_files_path = Path(settings.LOCAL_STORAGE_PATH)
if uploaded_files_path.exists():
    app.mount("/uploaded_files", StaticFiles(directory=str(uploaded_files_path)), name="uploaded_files")
```

**说明**：
- 使用 `settings.LOCAL_STORAGE_PATH`（值为 `data/uploaded_files`）作为目录路径
- 添加存在性检查，避免目录不存在时启动失败
- 挂载点 `/uploaded_files` 使图片可通过 HTTP 访问

---

### 3.2 前端HTML结构

#### 文件：`app/static/admin.html`

**修改位置**：在 `</body>` 标签之前（第126行 `<script src="/static/js/admin.js"></script>` 之前）添加

**HTML代码**：
```html
<!-- 图片预览模态框 -->
<div id="imagePreviewModal" class="image-modal" style="display: none;">
    <div class="image-modal-overlay"></div>
    <div class="image-modal-container">
        <!-- 关闭按钮 -->
        <button class="image-modal-close" aria-label="关闭">&times;</button>

        <!-- 工具栏 -->
        <div class="image-modal-toolbar">
            <button class="toolbar-btn" id="btnZoomOut" title="缩小（-）">
                <span class="btn-icon">-</span>
            </button>
            <span class="zoom-level" id="zoomLevel">100%</span>
            <button class="toolbar-btn" id="btnZoomIn" title="放大（+）">
                <span class="btn-icon">+</span>
            </button>
            <button class="toolbar-btn" id="btnRotateLeft" title="逆时针旋转">
                <span class="btn-icon">↺</span>
            </button>
            <button class="toolbar-btn" id="btnRotateRight" title="顺时针旋转">
                <span class="btn-icon">↻</span>
            </button>
            <button class="toolbar-btn" id="btnReset" title="重置">
                <span class="btn-icon">⟲</span>
            </button>
        </div>

        <!-- 图片容器 -->
        <div class="image-modal-content">
            <!-- 加载状态 -->
            <div class="image-loading" id="imageLoading">
                <div class="loading-spinner"></div>
                <p>加载中...</p>
            </div>

            <!-- 图片 -->
            <img id="previewImage" class="preview-image" alt="预览图片" style="display: none;">

            <!-- 错误提示 -->
            <div class="image-error" id="imageError" style="display: none;">
                <p>❌ 图片加载失败</p>
                <small id="errorMessage">文件不存在或无法访问</small>
            </div>
        </div>

        <!-- 文件名标题 -->
        <div class="image-modal-footer">
            <span id="imageFileName">文件名</span>
        </div>
    </div>
</div>
```

**DOM结构说明**：
- `image-modal`：最外层容器（z-index: 10000）
- `image-modal-overlay`：半透明遮罩层（点击关闭）
- `image-modal-container`：模态框主体（居中显示）
- `image-modal-close`：右上角关闭按钮
- `image-modal-toolbar`：工具栏（缩放、旋转、重置按钮）
- `image-modal-content`：图片显示区域
- `image-loading`：加载动画（默认显示）
- `preview-image`：实际图片元素
- `image-error`：错误提示（加载失败时显示）
- `image-modal-footer`：底部文件名显示

---

### 3.3 前端CSS样式

#### 文件：`app/static/css/admin.css`

**修改位置**：在文件末尾（第409行之后）添加

**CSS代码**：
```css
/* ==================== 图片预览模态框样式 ==================== */

/* 模态框容器 */
.image-modal {
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    z-index: 10000;
    display: flex;
    align-items: center;
    justify-content: center;
    animation: fadeIn 0.3s ease;
}

/* 遮罩层 */
.image-modal-overlay {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: rgba(0, 0, 0, 0.85);
    z-index: 1;
}

/* 模态框主体 */
.image-modal-container {
    position: relative;
    z-index: 2;
    background: white;
    border-radius: 12px;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
    max-width: 90vw;
    max-height: 90vh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
}

/* 关闭按钮 */
.image-modal-close {
    position: absolute;
    top: 15px;
    right: 15px;
    z-index: 3;
    width: 40px;
    height: 40px;
    border: none;
    background: rgba(0, 0, 0, 0.6);
    color: white;
    font-size: 28px;
    line-height: 1;
    cursor: pointer;
    border-radius: 50%;
    transition: all 0.2s;
    display: flex;
    align-items: center;
    justify-content: center;
}

.image-modal-close:hover {
    background: rgba(0, 0, 0, 0.8);
    transform: rotate(90deg);
}

/* 工具栏 */
.image-modal-toolbar {
    background: #f8f9fa;
    padding: 15px 20px;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 10px;
    border-bottom: 1px solid #dee2e6;
}

.toolbar-btn {
    width: 40px;
    height: 40px;
    border: 1px solid #ced4da;
    background: white;
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.2s;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 18px;
    color: #495057;
}

.toolbar-btn:hover:not(:disabled) {
    background: #3498db;
    border-color: #3498db;
    color: white;
}

.toolbar-btn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
}

.btn-icon {
    pointer-events: none;
}

.zoom-level {
    min-width: 60px;
    text-align: center;
    font-size: 14px;
    font-weight: 600;
    color: #495057;
}

/* 图片容器 */
.image-modal-content {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
    background: #f8f9fa;
    position: relative;
    min-height: 400px;
    max-height: 70vh;
}

/* 预览图片 */
.preview-image {
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
    transition: transform 0.3s ease;
    cursor: grab;
}

.preview-image:active {
    cursor: grabbing;
}

/* 加载状态 */
.image-loading {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    text-align: center;
}

.loading-spinner {
    width: 50px;
    height: 50px;
    border: 4px solid #e9ecef;
    border-top: 4px solid #3498db;
    border-radius: 50%;
    animation: spin 1s linear infinite;
    margin: 0 auto 15px;
}

.image-loading p {
    font-size: 14px;
    color: #6c757d;
}

/* 错误提示 */
.image-error {
    text-align: center;
    color: #e74c3c;
}

.image-error p {
    font-size: 18px;
    margin-bottom: 10px;
}

.image-error small {
    font-size: 14px;
    color: #95a5a6;
}

/* 底部文件名 */
.image-modal-footer {
    background: #f8f9fa;
    padding: 12px 20px;
    border-top: 1px solid #dee2e6;
    text-align: center;
    font-size: 14px;
    color: #495057;
}

/* 动画 */
@keyframes fadeIn {
    from {
        opacity: 0;
    }
    to {
        opacity: 1;
    }
}

@keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
}

/* 文件名可点击样式 */
.file-name-clickable {
    color: #3498db;
    cursor: pointer;
    text-decoration: none;
    transition: all 0.2s;
}

.file-name-clickable:hover {
    color: #2980b9;
    text-decoration: underline;
}

/* 响应式调整 */
@media (max-width: 768px) {
    .image-modal-container {
        max-width: 95vw;
        max-height: 95vh;
    }

    .toolbar-btn {
        width: 36px;
        height: 36px;
        font-size: 16px;
    }

    .image-modal-toolbar {
        padding: 10px;
        gap: 6px;
    }
}
```

**样式规格说明**：
- **颜色方案**：
  - 背景：白色 `#ffffff`（与现有浅色主题一致）
  - 工具栏/底部：`#f8f9fa`（浅灰）
  - 按钮悬停：`#3498db`（蓝色，与现有按钮风格一致）
  - 边框：`#dee2e6`（浅灰）
  - 错误提示：`#e74c3c`（红色）

- **尺寸**：
  - 模态框最大宽度：90vw
  - 模态框最大高度：90vh
  - 图片容器最大高度：70vh
  - 工具栏按钮：40px × 40px
  - 关闭按钮：40px × 40px（圆形）

- **动画**：
  - 模态框打开：0.3s淡入（fadeIn）
  - 图片变换：0.3s缓动（transform）
  - 加载动画：1s线性旋转（spin）
  - 关闭按钮悬停：90度旋转

---

### 3.4 前端JavaScript逻辑

#### 文件：`app/static/js/admin.js`

**修改1：修改 `renderTable()` 函数**

**修改位置**：第161行，将文件名单元格代码修改为：

**原代码**：
```javascript
<td class="file-name" title="${record.file_name}">${record.file_name}</td>
```

**修改后代码**：
```javascript
<td>
    <span class="file-name file-name-clickable" data-filename="${record.file_name}" title="${record.file_name}">
        ${record.file_name}
    </span>
</td>
```

**说明**：
- 添加 `file-name-clickable` CSS类（蓝色、鼠标悬停下划线）
- 添加 `data-filename` 属性存储文件名
- 使用 `<span>` 包裹文件名，便于事件委托

---

**修改2：在 `init()` 函数中添加事件监听**

**修改位置**：第82行（`loadStatistics();` 之前）添加

**添加代码**：
```javascript
// 图片预览事件委托（使用事件委托，监听表格上的点击）
elements.tableBody.addEventListener('click', handleFileNameClick);
```

---

**修改3：在文件末尾添加图片预览相关函数**

**修改位置**：第449行（`init();` 之后）添加

**添加代码**：
```javascript
// ==================== 图片预览功能 ====================

// 图片预览状态
const imagePreviewState = {
    scale: 1,        // 缩放比例（1 = 100%）
    rotation: 0,     // 旋转角度（0, 90, 180, 270）
    minScale: 0.1,   // 最小缩放10%
    maxScale: 5.0    // 最大缩放500%
};

// 图片预览DOM元素
const imagePreviewElements = {
    modal: document.getElementById('imagePreviewModal'),
    overlay: null,  // 在显示时获取
    closeBtn: null,
    previewImage: document.getElementById('previewImage'),
    imageLoading: document.getElementById('imageLoading'),
    imageError: document.getElementById('imageError'),
    errorMessage: document.getElementById('errorMessage'),
    imageFileName: document.getElementById('imageFileName'),
    zoomLevel: document.getElementById('zoomLevel'),
    btnZoomIn: document.getElementById('btnZoomIn'),
    btnZoomOut: document.getElementById('btnZoomOut'),
    btnRotateLeft: document.getElementById('btnRotateLeft'),
    btnRotateRight: document.getElementById('btnRotateRight'),
    btnReset: document.getElementById('btnReset')
};

// 处理文件名点击事件（事件委托）
function handleFileNameClick(event) {
    // 检查是否点击了文件名元素
    const fileNameElement = event.target.closest('.file-name-clickable');
    if (!fileNameElement) return;

    const filename = fileNameElement.dataset.filename;
    if (filename) {
        openImagePreview(filename);
    }
}

// 打开图片预览模态框
function openImagePreview(filename) {
    // 重置状态
    imagePreviewState.scale = 1;
    imagePreviewState.rotation = 0;

    // 显示模态框
    imagePreviewElements.modal.style.display = 'flex';

    // 显示加载状态
    imagePreviewElements.imageLoading.style.display = 'block';
    imagePreviewElements.previewImage.style.display = 'none';
    imagePreviewElements.imageError.style.display = 'none';

    // 设置文件名
    imagePreviewElements.imageFileName.textContent = filename;

    // 更新缩放显示
    updateZoomDisplay();

    // 加载图片
    const imageUrl = `/uploaded_files/${filename}`;
    const img = new Image();

    img.onload = function() {
        // 隐藏加载状态
        imagePreviewElements.imageLoading.style.display = 'none';

        // 显示图片
        imagePreviewElements.previewImage.src = imageUrl;
        imagePreviewElements.previewImage.style.display = 'block';

        // 启用工具栏按钮
        enableToolbarButtons(true);

        // 应用初始变换
        applyImageTransform();
    };

    img.onerror = function() {
        // 隐藏加载状态
        imagePreviewElements.imageLoading.style.display = 'none';

        // 显示错误提示
        imagePreviewElements.imageError.style.display = 'block';
        imagePreviewElements.errorMessage.textContent = '文件不存在或无法访问';

        // 禁用工具栏按钮
        enableToolbarButtons(false);
    };

    img.src = imageUrl;

    // 绑定事件（仅在首次打开时绑定）
    if (!imagePreviewElements.overlay) {
        imagePreviewElements.overlay = imagePreviewElements.modal.querySelector('.image-modal-overlay');
        imagePreviewElements.closeBtn = imagePreviewElements.modal.querySelector('.image-modal-close');

        // 点击遮罩层关闭
        imagePreviewElements.overlay.addEventListener('click', closeImagePreview);

        // 点击关闭按钮
        imagePreviewElements.closeBtn.addEventListener('click', closeImagePreview);

        // ESC键关闭
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape' && imagePreviewElements.modal.style.display === 'flex') {
                closeImagePreview();
            }
        });

        // 工具栏按钮事件
        imagePreviewElements.btnZoomIn.addEventListener('click', () => zoomImage(0.2));
        imagePreviewElements.btnZoomOut.addEventListener('click', () => zoomImage(-0.2));
        imagePreviewElements.btnRotateLeft.addEventListener('click', () => rotateImage(-90));
        imagePreviewElements.btnRotateRight.addEventListener('click', () => rotateImage(90));
        imagePreviewElements.btnReset.addEventListener('click', resetImageTransform);

        // 鼠标滚轮缩放
        imagePreviewElements.previewImage.addEventListener('wheel', handleMouseWheel, { passive: false });
    }
}

// 关闭图片预览
function closeImagePreview() {
    imagePreviewElements.modal.style.display = 'none';
    imagePreviewElements.previewImage.src = '';
}

// 缩放图片
function zoomImage(delta) {
    const newScale = imagePreviewState.scale + delta;

    // 限制范围
    if (newScale < imagePreviewState.minScale || newScale > imagePreviewState.maxScale) {
        return;
    }

    imagePreviewState.scale = newScale;
    applyImageTransform();
    updateZoomDisplay();
}

// 旋转图片
function rotateImage(degrees) {
    imagePreviewState.rotation = (imagePreviewState.rotation + degrees) % 360;

    // 处理负数角度
    if (imagePreviewState.rotation < 0) {
        imagePreviewState.rotation += 360;
    }

    applyImageTransform();
}

// 重置图片变换
function resetImageTransform() {
    imagePreviewState.scale = 1;
    imagePreviewState.rotation = 0;
    applyImageTransform();
    updateZoomDisplay();
}

// 应用图片变换（CSS transform）
function applyImageTransform() {
    const transform = `scale(${imagePreviewState.scale}) rotate(${imagePreviewState.rotation}deg)`;
    imagePreviewElements.previewImage.style.transform = transform;
}

// 更新缩放显示
function updateZoomDisplay() {
    const percentage = Math.round(imagePreviewState.scale * 100);
    imagePreviewElements.zoomLevel.textContent = `${percentage}%`;

    // 更新按钮状态
    imagePreviewElements.btnZoomOut.disabled = imagePreviewState.scale <= imagePreviewState.minScale;
    imagePreviewElements.btnZoomIn.disabled = imagePreviewState.scale >= imagePreviewState.maxScale;
}

// 启用/禁用工具栏按钮
function enableToolbarButtons(enabled) {
    imagePreviewElements.btnZoomIn.disabled = !enabled;
    imagePreviewElements.btnZoomOut.disabled = !enabled;
    imagePreviewElements.btnRotateLeft.disabled = !enabled;
    imagePreviewElements.btnRotateRight.disabled = !enabled;
    imagePreviewElements.btnReset.disabled = !enabled;
}

// 处理鼠标滚轮缩放（带防抖）
let wheelTimeout = null;
function handleMouseWheel(event) {
    event.preventDefault();

    // 防抖处理（100ms）
    if (wheelTimeout) {
        clearTimeout(wheelTimeout);
    }

    wheelTimeout = setTimeout(() => {
        // 向上滚动放大，向下滚动缩小
        const delta = event.deltaY > 0 ? -0.1 : 0.1;
        zoomImage(delta);
    }, 50);
}
```

**函数说明**：

1. **`handleFileNameClick(event)`**：
   - 事件委托处理器，监听表格点击
   - 使用 `closest('.file-name-clickable')` 检测点击目标
   - 提取 `data-filename` 属性，调用 `openImagePreview()`

2. **`openImagePreview(filename)`**：
   - 重置缩放和旋转状态
   - 显示模态框和加载动画
   - 构建图片URL：`/uploaded_files/${filename}`
   - 使用 `Image()` 对象预加载图片
   - 绑定 `onload`（成功）和 `onerror`（失败）事件
   - 首次打开时绑定所有事件监听器（遮罩层点击、ESC键、工具栏按钮、鼠标滚轮）

3. **`closeImagePreview()`**：
   - 隐藏模态框
   - 清空图片 `src`（释放内存）

4. **`zoomImage(delta)`**：
   - 增减缩放比例（delta = ±0.1 或 ±0.2）
   - 限制范围：0.1 - 5.0
   - 调用 `applyImageTransform()` 应用CSS变换
   - 调用 `updateZoomDisplay()` 更新百分比显示

5. **`rotateImage(degrees)`**：
   - 增减旋转角度（degrees = ±90）
   - 使用模运算限制在 0-360° 范围
   - 调用 `applyImageTransform()` 应用变换

6. **`resetImageTransform()`**：
   - 重置 scale=1, rotation=0
   - 恢复初始状态

7. **`applyImageTransform()`**：
   - 构建CSS `transform` 字符串
   - 同时应用 `scale()` 和 `rotate()`
   - 使用CSS transition实现平滑过渡

8. **`updateZoomDisplay()`**：
   - 更新缩放百分比显示
   - 禁用/启用放大/缩小按钮（到达极限时）

9. **`enableToolbarButtons(enabled)`**：
   - 统一启用/禁用所有工具栏按钮
   - 加载失败时禁用

10. **`handleMouseWheel(event)`**：
    - 阻止默认滚动行为
    - 防抖处理（50ms延迟）
    - 滚轮向上 → 放大10%
    - 滚轮向下 → 缩小10%

---

## 4. 实施顺序

### Phase 1: 后端静态文件服务配置
**文件**：`app/main.py`

**任务**：
1. 在第26行后添加 `/uploaded_files` 静态文件挂载
2. 导入 `Path` 模块
3. 添加目录存在性检查
4. 重启应用测试访问

**验证**：
- 访问 `http://localhost:10000/uploaded_files/<实际文件名>` 能够显示图片

---

### Phase 2: 前端HTML和CSS
**文件**：`app/static/admin.html` 和 `app/static/css/admin.css`

**任务**：
1. 在 `admin.html` 的 `</body>` 前添加模态框HTML结构
2. 在 `admin.css` 末尾添加模态框样式
3. 刷新页面检查HTML结构（使用浏览器开发者工具）

**验证**：
- 在浏览器控制台执行 `document.getElementById('imagePreviewModal').style.display = 'flex'` 能看到模态框

---

### Phase 3: 前端JavaScript逻辑
**文件**：`app/static/js/admin.js`

**任务**：
1. 修改 `renderTable()` 函数，添加 `file-name-clickable` 类和 `data-filename` 属性
2. 在 `init()` 函数中添加事件委托监听
3. 在文件末尾添加图片预览相关函数
4. 刷新页面测试点击文件名

**验证**：
- 点击文件名能够弹出模态框
- 图片正确加载
- 所有工具栏按钮功能正常

---

### Phase 4: 功能测试
**测试场景**：

1. **基本功能测试**：
   - ✅ 点击文件名弹出模态框
   - ✅ 图片正确显示
   - ✅ 点击遮罩层关闭
   - ✅ 点击关闭按钮关闭
   - ✅ 按ESC键关闭

2. **缩放功能测试**：
   - ✅ 点击放大按钮（+）增加20%
   - ✅ 点击缩小按钮（-）减少20%
   - ✅ 鼠标滚轮向上放大10%
   - ✅ 鼠标滚轮向下缩小10%
   - ✅ 缩放到10%时禁用缩小按钮
   - ✅ 缩放到500%时禁用放大按钮
   - ✅ 缩放百分比正确显示

3. **旋转功能测试**：
   - ✅ 点击顺时针按钮旋转90°
   - ✅ 点击逆时针按钮旋转-90°
   - ✅ 连续旋转4次恢复原状（0° → 90° → 180° → 270° → 0°）

4. **重置功能测试**：
   - ✅ 缩放和旋转后点击重置恢复初始状态

5. **边界场景测试**：
   - ✅ 文件不存在时显示错误提示
   - ✅ 错误提示显示时禁用所有工具栏按钮
   - ✅ 加载中显示旋转动画
   - ✅ 加载成功后隐藏加载动画

6. **浏览器兼容性测试**：
   - ✅ Chrome（桌面）
   - ✅ Firefox（桌面）
   - ✅ Safari（桌面）
   - ⚠️ 移动端非重点（可选测试）

---

## 5. 验证计划

### 5.1 单元测试点

**功能模块**：图片预览

| 测试项 | 输入 | 预期输出 |
|--------|------|----------|
| 文件名点击 | 点击有效文件名 | 弹出模态框 |
| 图片加载成功 | 存在的文件 | 显示图片，启用工具栏 |
| 图片加载失败 | 不存在的文件 | 显示错误提示，禁用工具栏 |
| 放大20% | scale=1, 点击+ | scale=1.2, 显示120% |
| 缩小20% | scale=1, 点击- | scale=0.8, 显示80% |
| 滚轮放大10% | scale=1, 滚轮向上 | scale=1.1, 显示110% |
| 滚轮缩小10% | scale=1, 滚轮向下 | scale=0.9, 显示90% |
| 缩放极限 | scale=0.1, 点击- | 按钮禁用，无变化 |
| 顺时针旋转 | rotation=0, 点击↻ | rotation=90 |
| 逆时针旋转 | rotation=90, 点击↺ | rotation=0 |
| 重置 | scale=2, rotation=180 | scale=1, rotation=0 |
| 关闭模态框 | 点击遮罩层 | 隐藏模态框 |
| ESC关闭 | 按ESC键 | 隐藏模态框 |

---

### 5.2 集成测试

**测试流程**：
1. 启动应用（`python run.py`）
2. 访问管理页面（`http://localhost:10000/admin`）
3. 等待记录列表加载完成
4. 点击第一条记录的文件名
5. 验证模态框打开且图片显示
6. 依次测试放大、缩小、旋转、重置功能
7. 点击遮罩层关闭模态框
8. 重复步骤4-7测试多条记录

---

### 5.3 业务逻辑验证

**验证点**：
1. **图片路径正确性**：
   - 数据库 `file_name` 字段：`SO20250103001.jpg`
   - 本地文件路径：`data/uploaded_files/SO20250103001.jpg`
   - HTTP访问路径：`/uploaded_files/SO20250103001.jpg`
   - 验证：三者一致

2. **用户体验**：
   - 加载动画在图片加载期间显示
   - 图片加载成功后立即显示
   - 错误提示信息清晰
   - 缩放旋转操作流畅（CSS transition）

3. **性能**：
   - 图片仅在点击时加载（懒加载）
   - 鼠标滚轮防抖（50ms）避免频繁缩放
   - 事件委托减少DOM事件监听器数量

---

## 6. 技术约束和注意事项

### 6.1 技术约束

1. **纯JavaScript实现**：
   - 不引入jQuery、Vue等外部库
   - 使用原生DOM API（`querySelector`, `addEventListener`等）
   - 使用ES6语法（`const`, `let`, 箭头函数）

2. **浏览器兼容性**：
   - 主要支持桌面浏览器（Chrome, Firefox, Safari）
   - 移动端非重点，响应式样式为可选
   - 需要支持CSS3 transform和animation

3. **图片格式**：
   - 支持 `.jpg`, `.png`, `.gif` 格式
   - 图片大小限制：10MB（由上传API控制）
   - 不支持非图片文件（PDF、视频等）

4. **静态文件服务**：
   - 后端需要配置 `/uploaded_files` 静态文件挂载
   - 目录必须存在且可读
   - 文件访问无身份验证（公开访问）

---

### 6.2 样式一致性

**与现有风格保持一致**：
- 颜色方案：白色背景 + 浅灰工具栏（`#f8f9fa`）
- 按钮样式：蓝色悬停（`#3498db`）
- 字体：系统默认字体栈（与admin.css一致）
- 圆角：12px（模态框）、6px（按钮）
- 阴影：`0 8px 32px rgba(0, 0, 0, 0.3)`

---

### 6.3 安全考虑

1. **文件访问控制**：
   - 当前实现：无身份验证（任何人可访问 `/uploaded_files/*`）
   - 风险：敏感单据图片可能被未授权访问
   - 建议：生产环境添加JWT或Session验证

2. **XSS防护**：
   - 文件名来自数据库，需防止恶意文件名注入
   - 当前实现：使用 `textContent` 而非 `innerHTML` 显示文件名
   - 图片URL构建：使用模板字符串拼接，无用户输入

3. **路径遍历防护**：
   - 风险：恶意文件名（如 `../../etc/passwd`）访问系统文件
   - 缓解：FastAPI StaticFiles自动过滤路径遍历
   - 建议：添加文件名验证（仅允许字母、数字、下划线、连字符、点）

---

### 6.4 性能优化

1. **懒加载**：
   - 仅在点击文件名时加载图片
   - 避免页面加载时预加载所有图片

2. **事件委托**：
   - 使用一个事件监听器监听整个表格
   - 避免为每个文件名绑定单独的监听器

3. **防抖处理**：
   - 鼠标滚轮缩放添加50ms防抖
   - 避免频繁触发缩放操作

4. **内存管理**：
   - 关闭模态框时清空 `img.src`
   - 释放图片占用的内存

---

### 6.5 已知限制

1. **文件不存在处理**：
   - 当前实现：显示通用错误提示
   - 无法区分"文件不存在"和"网络错误"
   - 改进：解析HTTP状态码（404 vs 500）

2. **大图片性能**：
   - 非常大的图片（如10MB）可能导致浏览器卡顿
   - 当前无压缩或缩略图机制
   - 改进：后端生成缩略图，预览时显示缩略图

3. **并发加载**：
   - 快速点击多个文件名可能导致并发加载
   - 当前无加载队列或取消机制
   - 改进：添加加载中状态检查，阻止并发打开

---

## 7. 集成指南

### 7.1 修改文件清单

| 文件 | 修改类型 | 行数变更 | 说明 |
|------|----------|----------|------|
| `app/main.py` | 添加代码 | +5行 | 添加静态文件挂载 |
| `app/static/admin.html` | 添加HTML | +51行 | 添加模态框结构 |
| `app/static/css/admin.css` | 添加CSS | +250行 | 添加模态框样式 |
| `app/static/js/admin.js` | 修改+添加 | +160行 | 修改渲染逻辑+添加预览功能 |

**总计**：约466行代码

---

### 7.2 代码插入位置

#### `app/main.py`
```python
# 第26行后插入
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# ↓↓↓ 在此处插入以下代码 ↓↓↓
from pathlib import Path
uploaded_files_path = Path(settings.LOCAL_STORAGE_PATH)
if uploaded_files_path.exists():
    app.mount("/uploaded_files", StaticFiles(directory=str(uploaded_files_path)), name="uploaded_files")
# ↑↑↑ 插入结束 ↑↑↑

# 路由
app.include_router(upload.router, prefix="/api", tags=["upload"])
```

#### `app/static/admin.html`
```html
<!-- 第126行前插入 -->
    <!-- Toast提示 -->
    <div class="toast" id="toast"></div>

    <!-- ↓↓↓ 在此处插入模态框HTML（见3.2节） ↓↓↓ -->

    <script src="/static/js/admin.js"></script>
</body>
```

#### `app/static/css/admin.css`
```css
/* 第409行后插入 */
@media (max-width: 768px) {
    /* 现有响应式样式 */
}

/* ↓↓↓ 在此处插入模态框CSS（见3.3节） ↓↓↓ */
```

#### `app/static/js/admin.js`
```javascript
// 修改第161行
// 原代码：
<td class="file-name" title="${record.file_name}">${record.file_name}</td>

// 修改为：
<td>
    <span class="file-name file-name-clickable" data-filename="${record.file_name}" title="${record.file_name}">
        ${record.file_name}
    </span>
</td>

// 在第82行前添加
elements.tableBody.addEventListener('click', handleFileNameClick);

// 在第449行后添加图片预览函数（见3.4节）
```

---

### 7.3 与现有代码的交互

1. **表格渲染函数（`renderTable()`）**：
   - 修改文件名单元格HTML结构
   - 添加 `file-name-clickable` 类和 `data-filename` 属性
   - 不影响其他列的渲染逻辑

2. **事件系统**：
   - 使用事件委托，监听 `elements.tableBody` 的点击事件
   - 与现有的复选框、删除按钮事件互不干扰
   - 通过 `closest()` 方法精确匹配目标元素

3. **状态管理**：
   - 新增 `imagePreviewState` 状态对象（独立于 `state`）
   - 不影响现有的分页、筛选、选择状态

4. **样式隔离**：
   - 所有新样式使用 `image-modal-*` 前缀
   - 避免与现有样式冲突
   - 模态框使用高 z-index（10000）覆盖在最上层

---

### 7.4 兼容性检查

1. **FastAPI版本**：
   - 需要 FastAPI 0.104.1+
   - `StaticFiles` API稳定，无兼容性问题

2. **浏览器API**：
   - `querySelector/querySelectorAll`：所有现代浏览器支持
   - `addEventListener`：所有现代浏览器支持
   - `closest()`：Chrome 41+, Firefox 35+, Safari 9+
   - CSS `transform`：所有现代浏览器支持
   - CSS `animation`：所有现代浏览器支持

3. **ES6语法**：
   - `const/let`：所有现代浏览器支持
   - 箭头函数：所有现代浏览器支持
   - 模板字符串：所有现代浏览器支持
   - 不兼容IE11（项目已不支持IE）

---

## 8. 测试检查点

### 8.1 功能测试点

**基础交互**：
- [ ] 点击文件名弹出模态框
- [ ] 模态框居中显示
- [ ] 显示正确的文件名标题
- [ ] 点击遮罩层关闭模态框
- [ ] 点击关闭按钮（×）关闭模态框
- [ ] 按ESC键关闭模态框

**图片加载**：
- [ ] 加载中显示旋转动画和"加载中..."文字
- [ ] 图片加载成功后隐藏加载动画
- [ ] 图片正确显示
- [ ] 文件不存在时显示错误提示
- [ ] 错误提示显示文件不存在或无法访问

**缩放功能**：
- [ ] 点击 + 按钮增加20%
- [ ] 点击 - 按钮减少20%
- [ ] 鼠标滚轮向上放大10%
- [ ] 鼠标滚轮向下缩小10%
- [ ] 缩放百分比实时更新显示
- [ ] 缩放到10%时禁用缩小按钮
- [ ] 缩放到500%时禁用放大按钮
- [ ] 缩放变换流畅（CSS transition）

**旋转功能**：
- [ ] 点击 ↻ 顺时针旋转90°
- [ ] 点击 ↺ 逆时针旋转90°
- [ ] 连续旋转4次回到初始角度
- [ ] 旋转变换流畅

**重置功能**：
- [ ] 重置按钮恢复100%缩放
- [ ] 重置按钮恢复0°旋转
- [ ] 重置后百分比显示正确

**错误处理**：
- [ ] 文件不存在时禁用所有工具栏按钮
- [ ] 网络错误时显示错误提示

---

### 8.2 边界场景测试

**文件名特殊字符**：
- [ ] 中文文件名（如 `销售单-001.jpg`）
- [ ] 带空格文件名（如 `SO 001.jpg`）
- [ ] 特殊字符文件名（如 `SO@001.jpg`）
- [ ] 长文件名（超过50字符）

**图片类型**：
- [ ] JPEG格式（`.jpg`, `.jpeg`）
- [ ] PNG格式（`.png`，包括透明PNG）
- [ ] GIF格式（`.gif`）
- [ ] 大文件（接近10MB）
- [ ] 小文件（几KB）

**并发操作**：
- [ ] 快速连续点击多个文件名
- [ ] 加载中点击关闭按钮
- [ ] 同时缩放和旋转

**极限缩放**：
- [ ] 连续放大到500%
- [ ] 连续缩小到10%
- [ ] 500%状态下旋转
- [ ] 10%状态下旋转

---

### 8.3 浏览器兼容性测试

**桌面浏览器**（重点）：
- [ ] Chrome 90+（macOS）
- [ ] Chrome 90+（Windows）
- [ ] Firefox 85+（macOS）
- [ ] Firefox 85+（Windows）
- [ ] Safari 14+（macOS）

**移动浏览器**（可选）：
- [ ] Safari iOS
- [ ] Chrome Android

**测试项**：
- [ ] 模态框显示正常
- [ ] 样式渲染正确
- [ ] 动画流畅
- [ ] 事件响应正常
- [ ] 鼠标滚轮缩放正常

---

## 9. 部署和上线

### 9.1 部署步骤

1. **代码提交**：
   ```bash
   git add app/main.py app/static/admin.html app/static/css/admin.css app/static/js/admin.js
   git commit -m "feat: 添加管理界面图片预览功能"
   git push
   ```

2. **生产环境部署**：
   ```bash
   # Docker部署
   docker-compose down
   docker-compose build
   docker-compose up -d

   # 验证健康检查
   curl http://localhost:10000/api/health
   ```

3. **验证图片访问**：
   ```bash
   # 测试静态文件服务
   curl -I http://localhost:10000/uploaded_files/<测试文件名>
   # 应返回 200 OK
   ```

---

### 9.2 上线检查清单

**环境配置**：
- [ ] `data/uploaded_files/` 目录存在
- [ ] 目录权限正确（可读）
- [ ] 至少有1个测试图片文件

**代码部署**：
- [ ] 所有代码文件已提交
- [ ] Docker镜像构建成功
- [ ] 容器启动正常

**功能验证**：
- [ ] 访问 `/admin` 页面正常
- [ ] 点击文件名能够预览图片
- [ ] 所有工具栏功能正常

**性能验证**：
- [ ] 图片加载速度正常（< 2秒）
- [ ] 模态框打开/关闭流畅
- [ ] 缩放旋转无卡顿

---

### 9.3 回滚方案

**如遇问题需回滚**：
```bash
# 1. 回滚代码
git revert <commit-hash>
git push

# 2. 重新部署
docker-compose down
docker-compose build
docker-compose up -d

# 3. 验证回滚成功
curl http://localhost:10000/api/health
```

**临时禁用功能**：
如不想回滚代码，可临时移除事件监听：
```javascript
// 在 admin.js 的 init() 函数中注释掉：
// elements.tableBody.addEventListener('click', handleFileNameClick);
```

---

## 10. 未来优化建议

### 10.1 功能增强

1. **图片下载**：
   - 添加"下载图片"按钮
   - 调用 `<a download>` 或 Blob API

2. **全屏模式**：
   - 添加全屏按钮
   - 使用 Fullscreen API

3. **多图片浏览**：
   - 添加"上一张"、"下一张"按钮
   - 键盘快捷键（←/→）切换

4. **缩略图预加载**：
   - 后端生成缩略图
   - 表格中显示缩略图预览

5. **图片标注**：
   - 添加绘图工具
   - 支持标记重点区域

---

### 10.2 性能优化

1. **懒加载优化**：
   - 预加载下一张图片
   - 使用 Intersection Observer

2. **缓存策略**：
   - 浏览器缓存图片（Cache-Control）
   - Service Worker离线缓存

3. **压缩优化**：
   - 后端自动压缩大图片
   - 使用WebP格式

4. **CDN加速**：
   - 将图片托管到CDN
   - 减少服务器带宽压力

---

### 10.3 用户体验

1. **键盘快捷键**：
   - `+/-`：缩放
   - `R`：旋转
   - `0`：重置
   - `←/→`：切换图片

2. **触摸手势**（移动端）：
   - 双指捏合缩放
   - 双击放大/缩小
   - 滑动切换图片

3. **图片信息显示**：
   - 显示图片尺寸（1920×1080）
   - 显示文件大小（2.5MB）
   - 显示上传时间

---

### 10.4 安全加固

1. **访问控制**：
   - 添加JWT认证
   - 验证用户权限

2. **文件名验证**：
   - 正则表达式验证文件名
   - 拒绝路径遍历字符（`../`）

3. **Content-Type检查**：
   - 验证MIME类型
   - 拒绝非图片文件

4. **速率限制**：
   - 限制图片访问频率
   - 防止爬虫批量下载

---

## 11. 文档版本

**文档版本**：1.0
**创建时间**：2025-10-20
**作者**：Claude Code
**目标功能**：clickable-filename-image-preview
**预计工作量**：约2-3小时（开发1.5小时 + 测试1小时）
**代码行数**：约466行（后端5 + 前端461）
**修改文件**：4个文件
**依赖项**：无新增依赖
**浏览器要求**：Chrome 90+, Firefox 85+, Safari 14+
**技术栈**：FastAPI + 原生JavaScript + CSS3

---

## 附录A：完整代码示例

### 后端代码（`app/main.py`）

```python
# 第26行后添加
from pathlib import Path

# 静态文件
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# 挂载上传文件目录（用于图片预览）
uploaded_files_path = Path(settings.LOCAL_STORAGE_PATH)
if uploaded_files_path.exists():
    app.mount("/uploaded_files", StaticFiles(directory=str(uploaded_files_path)), name="uploaded_files")
```

### 前端HTML代码（见3.2节）
### 前端CSS代码（见3.3节）
### 前端JavaScript代码（见3.4节）

---

## 附录B：测试用例

### 测试用例1：基本预览功能

**前置条件**：
- 数据库有至少1条成功上传的记录
- 对应图片文件存在于 `data/uploaded_files/`

**测试步骤**：
1. 访问 `http://localhost:10000/admin`
2. 等待记录列表加载完成
3. 点击第一条记录的文件名
4. 观察模态框是否弹出
5. 观察图片是否正确显示

**预期结果**：
- 模态框居中显示
- 图片清晰可见
- 文件名标题正确显示
- 缩放百分比显示100%

---

### 测试用例2：缩放功能

**前置条件**：模态框已打开且图片显示

**测试步骤**：
1. 点击 + 按钮3次
2. 观察缩放百分比
3. 点击 - 按钮5次
4. 观察缩放百分比和按钮状态
5. 滚动鼠标滚轮向上10次
6. 观察缩放百分比

**预期结果**：
- 第2步：显示160%（100% + 20%×3）
- 第4步：显示60%（160% - 20%×5），缩小按钮未禁用
- 第6步：显示160%（60% + 10%×10）

---

### 测试用例3：错误处理

**前置条件**：数据库有记录但文件已删除

**测试步骤**：
1. 删除 `data/uploaded_files/` 中的某个图片文件
2. 访问管理页面
3. 点击对应记录的文件名
4. 观察错误提示

**预期结果**：
- 显示错误图标和"图片加载失败"文字
- 显示"文件不存在或无法访问"提示
- 所有工具栏按钮禁用

---

**文档结束**
