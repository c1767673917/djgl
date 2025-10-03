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
