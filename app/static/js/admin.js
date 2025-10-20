// 全局状态
const state = {
    currentPage: 1,
    pageSize: 20,
    totalPages: 1,
    totalRecords: 0,
    filters: {
        search: '',
        docType: '',
        productType: '',
        startDate: '',
        endDate: ''
    },
    selectedIds: new Set()  // 跟踪选中的记录ID
};

// 图片预览配置常量
const IMAGE_PREVIEW_CONFIG = {
    ZOOM_MIN: 0.1,              // 最小缩放比例 10%
    ZOOM_MAX: 5.0,              // 最大缩放比例 500%
    ZOOM_STEP_BUTTON: 0.2,      // 按钮缩放步长 20%
    ZOOM_STEP_WHEEL: 0.1,       // 滚轮缩放步长 10%
    WHEEL_DEBOUNCE_MS: 50,      // 滚轮防抖延迟 50ms
    IMAGE_PATH_PREFIX: '/uploaded_files/',  // 图片路径前缀
    LOAD_TIMEOUT_MS: 30000      // 图片加载超时 30秒
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
    productTypeFilter: document.getElementById('productTypeFilter'),
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

    // 删除相关
    btnBatchDelete: document.getElementById('btnBatchDelete'),
    selectAll: document.getElementById('selectAll'),

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

    // 删除相关事件
    elements.btnBatchDelete.addEventListener('click', handleBatchDelete);
    elements.selectAll.addEventListener('change', handleSelectAll);

    // 图片预览事件委托(使用事件委托,监听表格上的点击)
    elements.tableBody.addEventListener('click', handleFileNameClick);

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
        if (state.filters.productType) params.append('product_type', state.filters.productType);
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
            <td>${record.product_type || ''}</td>
            <td>${formatDateTime(record.upload_time)}</td>
            <td>
                <span class="file-name file-name-clickable" data-filename="${record.file_name}" title="${record.file_name}">
                    ${record.file_name}
                </span>
            </td>
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
    state.filters.productType = elements.productTypeFilter.value;
    state.filters.startDate = elements.startDateInput.value;
    state.filters.endDate = elements.endDateInput.value;

    state.currentPage = 1; // 重置到第一页
    loadRecords();
}

// 处理重置
function handleReset() {
    elements.searchInput.value = '';
    elements.docTypeFilter.value = '';
    elements.productTypeFilter.value = '';
    elements.startDateInput.value = '';
    elements.endDateInput.value = '';

    state.filters = {
        search: '',
        docType: '',
        productType: '',
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
        if (state.filters.productType) params.append('product_type', state.filters.productType);
        if (state.filters.startDate) params.append('start_date', state.filters.startDate);
        if (state.filters.endDate) params.append('end_date', state.filters.endDate);

        // 下载CSV
        window.location.href = `/api/admin/export?${params}`;

        showToast('开始导出...', 'success');

    } catch (error) {
        showToast('导出失败: ' + error.message, 'error');
    }
}

// 格式化日期时间（标准化为 YYYY-MM-DD HH:MM:SS 格式）
function formatDateTime(dateTimeStr) {
    if (!dateTimeStr) return '-';

    // 后端返回 ISO 8601 格式（如 '2025-10-15T14:30:45'）或标准格式
    // 直接解析字符串，不依赖浏览器时区，确保所有用户看到相同的北京时间
    const match = dateTimeStr.match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})/);
    if (match) {
        return `${match[1]}-${match[2]}-${match[3]} ${match[4]}:${match[5]}:${match[6]}`;
    }

    // 降级处理（兼容其他格式）
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

// ==================== 图片预览功能 ====================

// 图片预览状态
const imagePreviewState = {
    scale: 1,        // 缩放比例(1 = 100%)
    rotation: 0,     // 旋转角度(0, 90, 180, 270)
    minScale: IMAGE_PREVIEW_CONFIG.ZOOM_MIN,   // 最小缩放10%
    maxScale: IMAGE_PREVIEW_CONFIG.ZOOM_MAX    // 最大缩放500%
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

// 处理文件名点击事件(事件委托)
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

    // 加载图片（使用URL编码处理特殊字符）
    const imageUrl = `${IMAGE_PREVIEW_CONFIG.IMAGE_PATH_PREFIX}${encodeURIComponent(filename)}`;
    const img = new Image();

    // 添加加载超时处理
    let loadTimeout = setTimeout(() => {
        img.src = '';  // 取消加载
        imagePreviewElements.imageLoading.style.display = 'none';
        imagePreviewElements.imageError.style.display = 'block';
        imagePreviewElements.errorMessage.textContent = '图片加载超时，请检查网络';
        enableToolbarButtons(false);
    }, IMAGE_PREVIEW_CONFIG.LOAD_TIMEOUT_MS);

    img.onload = function() {
        clearTimeout(loadTimeout);

        // 隐藏加载状态
        imagePreviewElements.imageLoading.style.display = 'none';

        // 显示图片
        imagePreviewElements.previewImage.src = imageUrl;
        imagePreviewElements.previewImage.style.display = 'block';

        // 显示图片尺寸信息
        const sizeInfo = `${this.naturalWidth} × ${this.naturalHeight}`;
        imagePreviewElements.imageFileName.textContent = `${filename} (${sizeInfo})`;

        // 启用工具栏按钮
        enableToolbarButtons(true);

        // 应用初始变换
        applyImageTransform();
    };

    img.onerror = function() {
        clearTimeout(loadTimeout);

        // 隐藏加载状态
        imagePreviewElements.imageLoading.style.display = 'none';

        // 显示错误提示
        imagePreviewElements.imageError.style.display = 'block';
        imagePreviewElements.errorMessage.textContent = '文件不存在或无法访问';

        // 禁用工具栏按钮
        enableToolbarButtons(false);
    };

    img.src = imageUrl;

    // 绑定事件(仅在首次打开时绑定)
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
        imagePreviewElements.btnZoomIn.addEventListener('click', () => zoomImage(IMAGE_PREVIEW_CONFIG.ZOOM_STEP_BUTTON));
        imagePreviewElements.btnZoomOut.addEventListener('click', () => zoomImage(-IMAGE_PREVIEW_CONFIG.ZOOM_STEP_BUTTON));
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

// 应用图片变换(CSS transform)
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

// 处理鼠标滚轮缩放(带防抖)
let wheelTimeout = null;
function handleMouseWheel(event) {
    event.preventDefault();

    // 防抖处理
    if (wheelTimeout) {
        clearTimeout(wheelTimeout);
    }

    wheelTimeout = setTimeout(() => {
        // 向上滚动放大,向下滚动缩小
        const delta = event.deltaY > 0 ? -IMAGE_PREVIEW_CONFIG.ZOOM_STEP_WHEEL : IMAGE_PREVIEW_CONFIG.ZOOM_STEP_WHEEL;
        zoomImage(delta);
    }, IMAGE_PREVIEW_CONFIG.WHEEL_DEBOUNCE_MS);
}

// 启动应用
init();
