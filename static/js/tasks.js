// Render task content as text, including titles, paths and diagnostic messages.
function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, char => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[char]));
}

// Format dependencies to handle both string and array formats
function formatDependencies(deps) {
    if (!deps) return '';
    if (typeof deps === 'string') return deps;
    if (Array.isArray(deps)) return deps.join(', ');
    return String(deps);
}

// Task Management Dashboard JavaScript

let allTasks = [];
let currentFilter = 'all';
let autoRefreshInterval = null;
let isUpdating = false;
let requestVersion = 0;

// Initialize after page load
document.addEventListener('DOMContentLoaded', () => {
    loadTasks();
    setupFilters();
    startAutoRefresh();
});

// Load task list
async function loadTasks() {
    // Skip if currently updating status
    if (isUpdating) {
        return;
    }

    const version = ++requestVersion;
    
    try {
        const response = await fetch(projectApi + '/tasks');
        
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
            allTasks = data.tasks;
            renderTasks();
            updateStats();
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

// Render task list
function renderTasks() {
    const taskList = document.getElementById('taskList');

    // Filter tasks based on current filter
    const filteredTasks = currentFilter === 'all'
        ? allTasks
        : currentFilter === 'OPEN' 
            ? allTasks.filter(task => ['OPEN', 'TODO', 'PENDING'].includes(task.status))
            : currentFilter === 'DONE' 
                ? allTasks.filter(task => task.board?.integration === 'confirmed')
                : currentFilter === 'AWAITING_INTEGRATION' 
                    ? allTasks.filter(task => task.status === 'AWAITING_INTEGRATION' || (task.status === 'DONE' && task.board?.integration !== 'confirmed'))
                    : allTasks.filter(task => task.status === currentFilter);

    if (filteredTasks.length === 0) {
        taskList.innerHTML = `
            <div class="empty">
                <div class="empty-mark" aria-hidden="true">—</div>
                <p>暂无任务</p><p>该分类下还没有任务。</p>
            </div>
        `;
        return;
    }

    taskList.innerHTML = filteredTasks.map(task => {
        const displayStatus = (task.status === 'DONE' && task.board?.integration !== 'confirmed') 
            ? 'AWAITING_INTEGRATION' 
            : task.status;
        const displayText = (task.status === 'DONE' && task.board?.integration !== 'confirmed')
            ? '待确认集成'
            : getStatusText(task.status);
        
        const depsText = formatDependencies(task.dependencies);
        
        return `
        <a class="task-item" href="${projectPage}/task/${encodeURIComponent(task.id)}">
            <div class="task-header">
                <span class="task-id">#${escapeHtml(task.id)}</span>
                <span class="task-status ${escapeHtml(displayStatus)}">${escapeHtml(displayText)}</span>
            </div>
            <div class="task-title">${escapeHtml(task.title)}</div>
            <div class="task-meta">
                ${task.priority ? `<span>优先级：${escapeHtml(task.priority)}</span>` : ''}
                ${task.estimated_hours !== undefined ? `<span>预估：${escapeHtml(task.estimated_hours)}小时</span>` : ''}
                ${task.role ? `<span>角色：${escapeHtml(task.role)}</span>` : ''}
                ${task.model ? `<span>模型：${escapeHtml(task.model)}</span>` : ''}
                ${depsText ? `<span>依赖：${escapeHtml(depsText)}</span>` : ''}
                ${task.failed_attempts !== undefined ? `<span>失败次数：${escapeHtml(task.failed_attempts)}</span>` : ''}
            </div>
        </a>
    `;
    }).join('');
}

// Update statistics
async function updateStats() {
    const version = ++requestVersion;
    
    try {
        const response = await fetch(projectApi + '/board');
        
        // Check version before processing
        if (version !== requestVersion) {
            return;
        }
        
        const data = await response.json();

        // Check version again after async operation
        if (version !== requestVersion) {
            return;
        }

        if (data.success) {
            const stats = data.stats;
            document.getElementById('totalTasks').textContent = stats.total;
            document.getElementById('inProgress').textContent = stats.by_status.IN_PROGRESS || 0;
            document.getElementById('awaitingReview').textContent = stats.by_status.AWAITING_REVIEW || 0;
            document.getElementById('completed').textContent = stats.completed;
        } else {
            showError('统计数据加载失败：' + data.error);
        }
    } catch (error) {
        // Check version before showing error
        if (version !== requestVersion) {
            return;
        }
        showError('统计数据加载失败：' + error.message);
    }
}

// Setup filter buttons
function setupFilters() {
    const filterButtons = document.querySelectorAll('.filter-btn');

    filterButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            // Remove active class from all buttons
            filterButtons.forEach(b => { 
                b.classList.remove('active'); 
                b.setAttribute('aria-pressed', 'false'); 
            });
            // Add active class to current button
            btn.classList.add('active');
            btn.setAttribute('aria-pressed', 'true');

            // Update filter and re-render
            currentFilter = btn.dataset.filter;
            renderTasks();
        });
    });
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

// Show error message
function showError(message) {
    const taskList = document.getElementById('taskList');
    taskList.innerHTML = `<div class="error">${escapeHtml(message)}</div>`;
}

// Start auto-refresh (every 5 seconds)
function startAutoRefresh() {
    if (autoRefreshInterval) {
        clearInterval(autoRefreshInterval);
    }
    autoRefreshInterval = setInterval(() => {
        loadTasks();
    }, 5000);
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
        loadTasks(); // Refresh immediately
    }
});
