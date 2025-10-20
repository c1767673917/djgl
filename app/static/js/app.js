// 全局状态
const state = {
    businessId: '',
    docNumber: '',
    docType: '',
    productType: '',  // 产品类型(如:油脂/快消)
    selectedFiles: [],
    maxFiles: 10,
    maxFileSize: 10 * 1024 * 1024, // 10MB
    uploading: false,
    validating: false,  // 二维码验证进行中
    fileValidationStatus: new Map()  // 文件验证状态: file对象 -> {qrCodeDetected, urlMatched, detectedUrl}
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
    // 从URL查询参数提取参数
    const urlParams = new URLSearchParams(window.location.search);
    state.businessId = urlParams.get('business_id');
    state.docNumber = urlParams.get('doc_number');
    state.docType = urlParams.get('doc_type');
    state.productType = urlParams.get('product_type') || '';  // 产品类型(可选参数)

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

    // 根据单据类型设置主题色
    setThemeByDocType(state.docType);

    // 绑定事件
    elements.uploadArea.addEventListener('click', () => elements.fileInput.click());
    elements.fileInput.addEventListener('change', handleFileSelect);
    elements.btnClear.addEventListener('click', clearFiles);
    elements.btnUpload.addEventListener('click', uploadFiles);
    elements.btnHistory.addEventListener('click', showHistory);
    elements.btnCloseModal.addEventListener('click', () => elements.historyModal.style.display = 'none');
}

// 根据单据类型设置主题
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

// 文件选择处理
async function handleFileSelect(e) {
    const files = Array.from(e.target.files);

    // 验证文件数量
    if (state.selectedFiles.length + files.length > state.maxFiles) {
        showToast(`最多只能选择${state.maxFiles}张图片`, 'error');
        return;
    }

    // 验证文件
    const validFiles = [];
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

        validFiles.push(file);
    }

    // 重置input
    e.target.value = '';

    if (validFiles.length === 0) {
        return;
    }

    // 二维码验证
    showValidationProgress(true, 0, validFiles.length);

    for (let i = 0; i < validFiles.length; i++) {
        const file = validFiles[i];
        showValidationProgress(true, i + 1, validFiles.length);

        try {
            // 添加3秒超时保护
            const timeoutPromise = new Promise((_, reject) =>
                setTimeout(() => reject(new Error('识别超时')), 3000)
            );

            const validationResult = await Promise.race([
                validateQRCode(file),
                timeoutPromise
            ]);

            if (validationResult.needsUserConfirmation) {
                // 需要用户确认
                const userDecision = await showValidationDialog(validationResult);

                if (userDecision === 'retake') {
                    // 用户选择重新拍照
                    showValidationProgress(false);
                    elements.fileInput.click();
                    return;
                } else if (userDecision === 'upload') {
                    // 用户选择仍然上传
                    state.selectedFiles.push(file);
                    state.fileValidationStatus.set(file, validationResult);
                }
            } else {
                // 验证通过,直接添加
                state.selectedFiles.push(file);
                state.fileValidationStatus.set(file, validationResult);
            }

        } catch (error) {
            // 验证失败,降级为普通上传
            console.error('QR code validation error:', error);
            showToast('二维码识别超时,已跳过验证', 'warning');
            state.selectedFiles.push(file);
            state.fileValidationStatus.set(file, { validationFailed: true, needsUserConfirmation: false });
        }
    }

    showValidationProgress(false);
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

            // 检查验证状态
            const validationStatus = state.fileValidationStatus.get(file);
            const hasWarning = validationStatus &&
                               !validationStatus.validationFailed &&
                               (validationStatus.needsUserConfirmation || !validationStatus.urlMatched);

            const warningClass = hasWarning ? 'has-warning' : '';
            const warningBadge = hasWarning ? `
                <div class="warning-badge" title="${validationStatus.message || '二维码验证警告'}">⚠️</div>
            ` : '';

            item.innerHTML = `
                <img src="${e.target.result}" alt="${file.name}" class="${warningClass}">
                ${warningBadge}
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
    state.fileValidationStatus.clear();
    updatePreview();
}

// 上传文件
async function uploadFiles() {
    if (state.uploading || state.selectedFiles.length === 0) {
        return;
    }

    // 检查是否有警告图片
    const warningCount = state.selectedFiles.filter(file => {
        const status = state.fileValidationStatus.get(file);
        return status && (status.needsUserConfirmation || !status.urlMatched);
    }).length;

    if (warningCount > 0) {
        const confirmed = confirm(`有${warningCount}张图片存在二维码验证警告,确认上传?`);
        if (!confirmed) {
            return;
        }
    }

    state.uploading = true;
    elements.btnUpload.disabled = true;
    elements.progressSection.style.display = 'block';
    elements.progressList.innerHTML = '';

    // 准备FormData
    const formData = new FormData();
    formData.append('business_id', state.businessId);
    formData.append('doc_number', state.docNumber);
    formData.append('doc_type', state.docType);
    if (state.productType) {
        formData.append('product_type', state.productType);  // 添加产品类型参数(如果存在)
    }
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
                        <div>时间: ${formatDateTime(record.upload_time)}</div>
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

// ===== 二维码验证相关函数 =====

/**
 * 验证图片中的二维码
 * @param {File} file - 图片文件
 * @returns {Promise<Object>} 验证结果
 */
async function validateQRCode(file) {
    // 检查jsQR库是否加载
    if (typeof jsQR !== 'function') {
        console.warn('QR code validation library not available, skipping validation');
        return { validationSkipped: true, needsUserConfirmation: false };
    }

    return new Promise((resolve, reject) => {
        const reader = new FileReader();

        reader.onload = (e) => {
            const img = new Image();

            img.onload = () => {
                try {
                    // 创建canvas进行图片解析
                    const canvas = document.createElement('canvas');
                    const context = canvas.getContext('2d');

                    // 大图片降采样处理
                    const MAX_SIZE = 2000;
                    let width = img.width;
                    let height = img.height;

                    if (width > MAX_SIZE || height > MAX_SIZE) {
                        const scale = Math.min(MAX_SIZE / width, MAX_SIZE / height);
                        width = Math.floor(width * scale);
                        height = Math.floor(height * scale);
                    }

                    canvas.width = width;
                    canvas.height = height;
                    context.drawImage(img, 0, 0, width, height);

                    const imageData = context.getImageData(0, 0, canvas.width, canvas.height);

                    // 使用jsQR识别二维码
                    const code = jsQR(imageData.data, imageData.width, imageData.height);

                    // 清理内存
                    canvas.width = 0;
                    canvas.height = 0;
                    img.src = '';

                    if (!code) {
                        // 未检测到二维码
                        resolve({
                            qrCodeDetected: false,
                            urlMatched: false,
                            detectedUrl: null,
                            needsUserConfirmation: true,
                            message: '未在图片中检测到二维码'
                        });
                        return;
                    }

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

                    // 只验证business_id，不验证doc_number
                    if (detectedParams.businessId === currentBusinessId) {
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
                            currentBusinessId: currentBusinessId,
                            needsUserConfirmation: true,
                            message: '二维码业务单据ID不一致'
                        });
                    }

                } catch (error) {
                    reject(error);
                }
            };

            img.onerror = () => reject(new Error('图片加载失败'));
            img.src = e.target.result;
        };

        reader.onerror = () => reject(new Error('文件读取失败'));
        reader.readAsDataURL(file);
    });
}

/**
 * 从URL中提取business_id
 * @param {string} url - 完整URL
 * @returns {Object|null} {businessId, docNumber, docType}或null
 */
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

/**
 * 显示验证进度
 * @param {boolean} show - 是否显示
 * @param {number} current - 当前进度
 * @param {number} total - 总数
 */
function showValidationProgress(show, current = 0, total = 0) {
    let progressOverlay = document.getElementById('qrValidationProgress');

    if (!progressOverlay) {
        // 创建进度遮罩层
        progressOverlay = document.createElement('div');
        progressOverlay.id = 'qrValidationProgress';
        progressOverlay.className = 'qr-validation-progress';
        progressOverlay.innerHTML = `
            <div class="spinner"></div>
            <p class="progress-text">正在识别二维码...</p>
        `;
        document.body.appendChild(progressOverlay);
    }

    if (show) {
        progressOverlay.style.display = 'flex';
        progressOverlay.querySelector('.progress-text').textContent =
            `正在识别二维码... (${current}/${total})`;
    } else {
        progressOverlay.style.display = 'none';
    }
}

/**
 * 显示验证结果对话框
 * @param {Object} result - 验证结果
 * @returns {Promise<string>} 用户决策: 'retake' | 'upload'
 */
function showValidationDialog(result) {
    return new Promise((resolve) => {
        // 移除已存在的对话框(如果有)
        const existingDialog = document.getElementById('qrValidationDialog');
        if (existingDialog) {
            document.body.removeChild(existingDialog);
        }

        // 创建对话框
        const dialog = document.createElement('div');
        dialog.id = 'qrValidationDialog';
        dialog.className = 'qr-validation-dialog';

        let message = '';
        if (!result.qrCodeDetected) {
            message = `
                <div class="dialog-icon warning">⚠️</div>
                <h3>未检测到二维码</h3>
                <p>未在图片中检测到二维码</p>
                <p class="hint">建议重新拍照确保二维码清晰可见</p>
            `;
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

        dialog.innerHTML = `
            <div class="dialog-content">
                ${message}
                <div class="dialog-actions">
                    <button class="btn-secondary" id="btnRetake">重新拍照</button>
                    <button class="btn-primary" id="btnUploadAnyway">仍然上传</button>
                </div>
            </div>
        `;

        document.body.appendChild(dialog);

        // 绑定事件
        dialog.querySelector('#btnRetake').addEventListener('click', () => {
            document.body.removeChild(dialog);
            resolve('retake');
        });

        dialog.querySelector('#btnUploadAnyway').addEventListener('click', () => {
            document.body.removeChild(dialog);
            resolve('upload');
        });
    });
}

// 启动应用
init();
