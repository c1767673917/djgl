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
