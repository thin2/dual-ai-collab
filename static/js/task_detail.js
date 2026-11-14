// Render titles, paths and diagnostic messages as text. Description and section bodies go through renderMarkdown.
function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, char => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[char]));
}

// Format dependencies to handle both string and array formats
function formatDependencies(deps) {
    if (!deps) return '无';
    if (typeof deps === 'string') return deps;
    if (Array.isArray(deps)) return deps.join(', ') || '无';
    return String(deps);
}

// Task Detail Page JavaScript

let taskData = null;
let autoRefreshInterval = null;
let isUpdating = false;
let requestVersion = 0;

// Initialize after page load
document.addEventListener('DOMContentLoaded', () => {
    loadTaskDetail();
    startAutoRefresh();
});

// Load task details
async function loadTaskDetail() {
    // Skip if currently updating status
    if (isUpdating) {
        return;
    }

    const version = ++requestVersion;
    
    try {
        const response = await fetch(`${projectApi}/tasks/${encodeURIComponent(taskId)}`);
        
        // Check version before processing response
        if (version !== requestVersion) {
            return;
        }
        
        const data = await response.json();

        // Check version again after async operation
        if (version !== requestVersion) {
            return;
        }

        if (data.success) {
            taskData = data.task;
            renderTaskDetail();
        } else {
            showError('加载任务失败：' + data.error);
        }
    } catch (error) {
        // Check version before showing error
        if (version !== requestVersion) {
            return;
        }
        showError('网络错误：' + error.message);
    }
}

// Render task details
function renderTaskDetail() {
    const container = document.getElementById('taskDetail');
    
    // Extract sections
    const getSection = (heading) => {
        if (!taskData.sections || !Array.isArray(taskData.sections)) return '';
        const section = taskData.sections.find(s => s.heading === heading);
        return section ? section.body : '';
    };
    
    const description = taskData.description || getSection('Task Description') || getSection('任务描述') || '无描述';
    
    // Render all sections except the ones we handle specially
    const specialHeadings = ['Task Description', '任务描述', 'Acceptance Criteria', '验收标准'];
    const otherSections = (taskData.sections || [])
        .filter(s => !specialHeadings.includes(s.heading) && s.heading !== '任务描述' && s.heading !== 'Task Description')
        .map(s => `
            <div class="detail-section">
                <h3 class="section-title">${escapeHtml(s.heading)}</h3>
                <div class="description">${renderMarkdown(s.body)}</div>
            </div>
        `).join('');
    
    // Acceptance criteria section
    const acceptanceCriteria = getSection('Acceptance Criteria') || getSection('验收标准');
    const acceptanceSection = acceptanceCriteria ? `
        <div class="detail-section">
            <h3 class="section-title">验收标准</h3>
            <div class="description">${renderMarkdown(acceptanceCriteria)}</div>
        </div>
    ` : '';
    
    // Parse files from the task
    const files = taskData.files || [];
    
    // Display status - show "Awaiting Integration" for unconfirmed DONE tasks
    const displayStatus = (taskData.status === 'DONE' && taskData.board?.integration !== 'confirmed')
        ? 'AWAITING_INTEGRATION'
        : taskData.status;
    const displayText = (taskData.status === 'DONE' && taskData.board?.integration !== 'confirmed')
        ? '待确认集成'
        : getStatusText(taskData.status);
    
    // Integration info
    let integrationInfo = '';
    if (taskData.integration) {
        integrationInfo = `
        <div class="detail-section">
            <h3 class="section-title">集成信息</h3>
            <div class="meta-grid">
                ${taskData.integration.commit ? `
                <div class="meta-item">
                    <div class="meta-label">提交</div>
                    <div class="meta-value">${escapeHtml(taskData.integration.commit)}</div>
                </div>` : ''}
                ${taskData.integration.timestamp ? `
                <div class="meta-item">
                    <div class="meta-label">时间</div>
                    <div class="meta-value">${escapeHtml(taskData.integration.timestamp)}</div>
                </div>` : ''}
                ${taskData.integration.note ? `
                <div class="meta-item">
                    <div class="meta-label">备注</div>
                    <div class="meta-value">${escapeHtml(taskData.integration.note)}</div>
                </div>` : ''}
            </div>
        </div>`;
    }
    
    // Preserve selected status before re-rendering
    const selectedStatus = document.getElementById('statusSelect')?.value || '';
    
    const depsText = formatDependencies(taskData.dependencies);
    
    container.innerHTML = `
        <div class="detail-header">
            <div class="detail-title-section">
                <span class="detail-id">#${escapeHtml(taskData.id)}</span>
                <h2>${escapeHtml(taskData.title)}</h2>
            </div>
            <div class="status-actions">
                <span class="task-status ${escapeHtml(displayStatus)}">${escapeHtml(displayText)}</span>
                <select id="statusSelect" class="status-select" aria-label="选择任务状态" ${isUpdating ? 'disabled' : ''}>
                    <option value="">选择新状态...</option>
                    <option value="PENDING">待处理</option>
                    <option value="OPEN">待办</option>
                    <option value="TODO">待办</option>
                    <option value="IN_PROGRESS">进行中</option>
                    <option value="AWAITING_REVIEW">待审查</option>
                    <option value="AWAITING_INTEGRATION">待确认集成</option>
                    <option value="REJECTED">已拒绝</option>
                    <option value="BLOCKED">阻塞</option>
                    <option value="FAILED">失败</option>
                </select>
                <button onclick="updateStatus()" class="update-btn" id="updateBtn" ${isUpdating ? 'disabled' : ''}>更新状态</button>
            </div>
        </div>

        <div class="detail-section">
            <h3 class="section-title">任务描述</h3>
            <div class="description">${renderMarkdown(description)}</div>
        </div>

        ${otherSections}

        ${acceptanceSection}

        <div class="detail-section">
            <h3 class="section-title">任务信息</h3>
            <div class="meta-grid">
                <div class="meta-item">
                    <div class="meta-label">优先级</div>
                    <div class="meta-value">${escapeHtml(taskData.priority || '未设置')}</div>
                </div>
                <div class="meta-item">
                    <div class="meta-label">预估小时</div>
                    <div class="meta-value">${taskData.estimated_hours !== undefined ? escapeHtml(taskData.estimated_hours) + '小时' : '未预估'}</div>
                </div>
                <div class="meta-item">
                    <div class="meta-label">角色</div>
                    <div class="meta-value">${escapeHtml(taskData.role || '当前会话直接执行')}</div>
                </div>
                <div class="meta-item">
                    <div class="meta-label">模型</div>
                    <div class="meta-value">${escapeHtml(taskData.model || (taskData.role ? '未配置' : '不适用'))}</div>
                </div>
                <div class="meta-item">
                    <div class="meta-label">Droid</div>
                    <div class="meta-value">${escapeHtml(taskData.droid || (taskData.role ? '未配置' : '不适用'))}</div>
                </div>
                <div class="meta-item">
                    <div class="meta-label">依赖</div>
                    <div class="meta-value">${escapeHtml(depsText)}</div>
                </div>
                <div class="meta-item">
                    <div class="meta-label">失败次数</div>
                    <div class="meta-value">${taskData.failed_attempts !== undefined ? escapeHtml(taskData.failed_attempts) : '0'}</div>
                </div>
            </div>
        </div>

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

        ${integrationInfo}

        ${taskData.board?.waiting && taskData.board.waiting.length > 0 ? `
        <div class="detail-section">
            <h3 class="section-title">等待中</h3>
            <div class="meta-value">${escapeHtml(taskData.board.waiting.join(', '))}</div>
        </div>
        ` : ''}
    `;
    
    // Restore selected status if it was set
    if (selectedStatus) {
        document.getElementById('statusSelect').value = selectedStatus;
    }
}

// Update task status
async function updateStatus() {
    const select = document.getElementById('statusSelect');
    const newStatus = select.value;

    if (!newStatus) {
        showMessage('请选择新状态', 'error');
        return;
    }

    // Check if already updating
    if (isUpdating) {
        showMessage('正在更新中，请稍候', 'error');
        return;
    }

    // Prevent setting DONE or VERIFIED directly
    if (newStatus === 'DONE' || newStatus === 'VERIFIED') {
        showMessage('无法直接设置 DONE 或 VERIFIED 状态。请使用 skill integrate 命令。', 'error');
        return;
    }

    const updateBtn = document.getElementById('updateBtn');
    const statusSelect = document.getElementById('statusSelect');
    updateBtn.disabled = true;
    statusSelect.disabled = true;
    updateBtn.textContent = '更新中...';
    
    // Stop auto-refresh during update and increment version
    isUpdating = true;
    ++requestVersion;
    stopAutoRefresh();

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
            // Reload task details immediately
            isUpdating = false;
            await loadTaskDetail();
            showMessage(data.message || '状态已更新', 'success');
        } else {
            showMessage('更新失败：' + data.error, 'error');
        }
    } catch (error) {
        showMessage('网络错误：' + error.message, 'error');
    } finally {
        isUpdating = false;
        updateBtn.disabled = false;
        statusSelect.disabled = false;
        updateBtn.textContent = '更新状态';
        if (!document.hidden) {
            startAutoRefresh();
        }
    }
}

// Show message
function showMessage(message, type) {
    const container = document.getElementById('messageContainer');
    if (!container) return;
    
    container.innerHTML = `<div class="message ${type}">${escapeHtml(message)}</div>`;

    // Cancel any pending clear timer
    if (window.messageClearTimer) {
        clearTimeout(window.messageClearTimer);
    }

    // Auto-hide after 5 seconds
    window.messageClearTimer = setTimeout(() => {
        if (container) {
            container.innerHTML = '';
        }
    }, 5000);
}

// Show error
function showError(message) {
    const container = document.getElementById('taskDetail');
    if (!taskData) {
        container.innerHTML = `<div class="error">${escapeHtml(message)}</div>`;
    } else {
        showMessage(message, 'error');
    }
}

// Get status text
function getStatusText(status) {
    const statusMap = {
        'PENDING': '待处理',
        'TODO': '待办',
        'OPEN': '待办',
        'IN_PROGRESS': '进行中',
        'AWAITING_REVIEW': '待审查',
        'AWAITING_INTEGRATION': '待确认集成',
        'DONE': '已完成',
        'VERIFIED': '已验证',
        'REJECTED': '已拒绝',
        'BLOCKED': '阻塞',
        'FAILED': '失败'
    };
    return statusMap[status] || status;
}

// Start auto-refresh (every 5 seconds)
function startAutoRefresh() {
    if (autoRefreshInterval) {
        clearInterval(autoRefreshInterval);
    }
    if (!isUpdating) {
        autoRefreshInterval = setInterval(() => {
            if (!isUpdating) {
                loadTaskDetail();
            }
        }, 5000);
    }
}

// Stop auto-refresh
function stopAutoRefresh() {
    if (autoRefreshInterval) {
        clearInterval(autoRefreshInterval);
        autoRefreshInterval = null;
    }
}

// Stop refresh when page loses focus, resume when regained
document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
        stopAutoRefresh();
    } else {
        startAutoRefresh();
        loadTaskDetail();
    }
});
