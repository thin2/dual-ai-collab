// Render task content as text, including titles, paths and diagnostic messages.
function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, char => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[char]));
}

// 任务详情页面 JavaScript

let taskData = null;
let autoRefreshInterval = null;

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', () => {
    loadTaskDetail();
    startAutoRefresh();
});

// 加载任务详情
async function loadTaskDetail() {
    try {
        const response = await fetch(`${projectApi}/tasks/${encodeURIComponent(taskId)}`);
        const data = await response.json();

        if (data.success) {
            taskData = data.task;
            renderTaskDetail();
        } else {
            showError('加载任务失败: ' + data.error);
        }
    } catch (error) {
        showError('网络错误: ' + error.message);
    }
}

// 渲染任务详情
function renderTaskDetail() {
    const container = document.getElementById('taskDetail');

    const section = heading => (taskData.sections || []).find(item => item.heading === heading)?.body || '';
    const lines = text => text.split('\n').map(line => line.replace(/^\s*[-*]\s*(?:\[[ xX]\]\s*)?/, '').trim()).filter(Boolean);
    const criteria = taskData.acceptance_criteria || lines(section('验收标准'));
    const files = taskData.related_files || lines(section('相关文件'));
    const selectedStatus = document.getElementById('statusSelect')?.value || '';
    container.innerHTML = `
        <div id="messageContainer" role="status"></div>

        <div class="detail-header">
            <div class="detail-title-section">
                <span class="detail-id">#${escapeHtml(taskData.id)}</span>
                <h2>${escapeHtml(taskData.title)}</h2>
            </div>
            <div class="status-actions">
                <span class="task-status ${escapeHtml(taskData.status)}">${escapeHtml(['DONE', 'VERIFIED'].includes(taskData.status) && taskData.board?.integration !== 'confirmed' ? '待确认集成' : getStatusText(taskData.status))}</span>
                <select id="statusSelect" class="status-select" aria-label="选择任务状态">
                    <option value="">选择新状态...</option>
                    <option value="OPEN">待办</option>
                    <option value="IN_PROGRESS">进行中</option>
                    <option value="AWAITING_REVIEW">待审查</option>
                    <option value="AWAITING_INTEGRATION">待集成</option>
                    <option value="DONE">已完成</option>
                    <option value="VERIFIED">已验证</option>
                </select>
                <button onclick="updateStatus()" class="update-btn" id="updateBtn">更新状态</button>
            </div>
        </div>

        <div class="detail-section">
            <h3 class="section-title">任务描述</h3>
            <div class="description">${escapeHtml(taskData.description || section('任务描述') || '尚未填写描述。')}</div>
        </div>

        <div class="detail-section">
            <h3 class="section-title">任务信息</h3>
            <div class="meta-grid">
                <div class="meta-item">
                    <div class="meta-label">优先级</div>
                    <div class="meta-value">${escapeHtml(taskData.priority || '未设置')}</div>
                </div>
                <div class="meta-item">
                    <div class="meta-label">预计时间</div>
                    <div class="meta-value">${escapeHtml(taskData.estimated_time || taskData.extra_fields?.['预计工时'] || '未估时')}</div>
                </div>
                <div class="meta-item">
                    <div class="meta-label">依赖任务</div>
                    <div class="meta-value">${escapeHtml(taskData.dependencies || taskData.depends_on || '无')}</div>
                </div>
                <div class="meta-item">
                    <div class="meta-label">分配给</div>
                    <div class="meta-value">${escapeHtml(taskData.assigned_to || '未分配')}</div>
                </div>
            </div>
        </div>

        ${criteria.length > 0 ? `
        <div class="detail-section">
            <h3 class="section-title">验收标准</h3>
            <ul class="criteria-list">
                ${criteria.map(criterion => `
                    <li>${escapeHtml(criterion)}</li>
                `).join('')}
            </ul>
        </div>
        ` : ''}

        ${files.length > 0 ? `
        <div class="detail-section">
            <h3 class="section-title">相关文件</h3>
            <div class="related-files">
                ${files.map(file => `
                    <span class="file-tag">${escapeHtml(file)}</span>
                `).join('')}
            </div>
        </div>
        ` : ''}
    `;
    document.getElementById('statusSelect').value = selectedStatus;
}

// 更新任务状态
async function updateStatus() {
    const select = document.getElementById('statusSelect');
    const newStatus = select.value;

    if (!newStatus) {
        showMessage('请选择新状态', 'error');
        return;
    }

    const updateBtn = document.getElementById('updateBtn');
    updateBtn.disabled = true;
    updateBtn.textContent = '更新中...';

    try {
        const response = await fetch(`${projectApi}/tasks/${encodeURIComponent(taskId)}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ status: newStatus })
        });

        const data = await response.json();

        if (data.success) {
            showMessage(data.message, 'success');
            // 重新加载任务详情
            setTimeout(() => {
                loadTaskDetail();
            }, 1000);
        } else {
            showMessage('更新失败: ' + data.error, 'error');
            updateBtn.disabled = false;
            updateBtn.textContent = '更新状态';
        }
    } catch (error) {
        showMessage('网络错误: ' + error.message, 'error');
        updateBtn.disabled = false;
        updateBtn.textContent = '更新状态';
    }
}

// 显示消息
function showMessage(message, type) {
    const container = document.getElementById('messageContainer');
    container.innerHTML = `<div class="message ${type}">${escapeHtml(message)}</div>`;

    // 3秒后自动隐藏
    setTimeout(() => {
        container.innerHTML = '';
    }, 3000);
}

// 显示错误
function showError(message) {
    const container = document.getElementById('taskDetail');
    container.innerHTML = `<div class="error">${escapeHtml(message)}</div>`;
}

// 获取状态文本
function getStatusText(status) {
    const statusMap = {
        'TODO': '待办',
        'OPEN': '待办',
        'IN_PROGRESS': '进行中',
        'AWAITING_REVIEW': '待审查',
        'AWAITING_INTEGRATION': '待集成',
        'DONE': '已完成',
        'VERIFIED': '已验证',
        'REJECTED': '已拒绝',
        'FAILED': '失败'
    };
    return statusMap[status] || status;
}

// 启动自动刷新（每 5 秒）
function startAutoRefresh() {
    autoRefreshInterval = setInterval(() => {
        loadTaskDetail();
    }, 5000);
}

// 停止自动刷新
function stopAutoRefresh() {
    if (autoRefreshInterval) {
        clearInterval(autoRefreshInterval);
        autoRefreshInterval = null;
    }
}

// 页面失去焦点时停止刷新，获得焦点时恢复
document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
        stopAutoRefresh();
    } else {
        startAutoRefresh();
        loadTaskDetail();
    }
});
