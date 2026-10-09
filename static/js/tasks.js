// Render task content as text, including titles, paths and diagnostic messages.
function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, char => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[char]));
}

// 任务管理面板 JavaScript

let allTasks = [];
let currentFilter = 'all';
let autoRefreshInterval = null;

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', () => {
    loadTasks();
    setupFilters();
    startAutoRefresh();
});

// 加载任务列表
async function loadTasks() {
    try {
        const response = await fetch(projectApi + '/tasks');
        const data = await response.json();

        if (data.success) {
            allTasks = data.tasks;
            renderTasks();
            updateStats();
        } else {
            showError('加载任务失败: ' + data.error);
        }
    } catch (error) {
        showError('网络错误: ' + error.message);
    }
}

// 渲染任务列表
function renderTasks() {
    const taskList = document.getElementById('taskList');

    // 根据当前筛选条件过滤任务
    const filteredTasks = currentFilter === 'all'
        ? allTasks
        : allTasks.filter(task => currentFilter === 'OPEN' ? ['OPEN', 'TODO'].includes(task.status) : currentFilter === 'DONE' ? task.board?.integration === 'confirmed' : currentFilter === 'AWAITING_INTEGRATION' ? (task.status === 'AWAITING_INTEGRATION' || (['DONE', 'VERIFIED'].includes(task.status) && task.board?.integration !== 'confirmed')) : task.status === currentFilter);

    if (filteredTasks.length === 0) {
        taskList.innerHTML = `
            <div class="empty">
                <div class="empty-mark" aria-hidden="true">—</div>
                <p>这里暂时留白</p><p>当前分类还没有任务。</p>
            </div>
        `;
        return;
    }

    taskList.innerHTML = filteredTasks.map(task => `
        <a class="task-item" href="${projectPage}/task/${encodeURIComponent(task.id)}">
            <div class="task-header">
                <span class="task-id">#${escapeHtml(task.id)}</span>
                <span class="task-status ${escapeHtml(task.status)}">${escapeHtml(['DONE', 'VERIFIED'].includes(task.status) && task.board?.integration !== 'confirmed' ? '待确认集成' : getStatusText(task.status))}</span>
            </div>
            <div class="task-title">${escapeHtml(task.title)}</div>
            <div class="task-meta">
                <span>优先级: ${escapeHtml(task.priority || '未设置')}</span>
                <span>预计: ${escapeHtml(task.estimated_time || task.extra_fields?.['预计工时'] || '未估时')}</span>
                ${(task.dependencies && task.dependencies !== '无') ? `<span>依赖 ${escapeHtml(task.dependencies)}</span>` : ''}
            </div>
        </a>
    `).join('');
}

// 更新统计信息
async function updateStats() {
    try {
        const response = await fetch(projectApi + '/board');
        const data = await response.json();

        if (data.success) {
            const stats = data.stats;
            document.getElementById('totalTasks').textContent = stats.total;
            document.getElementById('inProgress').textContent = stats.by_status.IN_PROGRESS || 0;
            document.getElementById('awaitingReview').textContent = stats.by_status.AWAITING_REVIEW || 0;
            document.getElementById('completed').textContent = stats.completed;
        }
    } catch (error) {
        console.error('更新统计失败:', error);
    }
}

// 设置筛选按钮
function setupFilters() {
    const filterButtons = document.querySelectorAll('.filter-btn');

    filterButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            // 移除所有按钮的 active 类
            filterButtons.forEach(b => { b.classList.remove('active'); b.setAttribute('aria-pressed', 'false'); });
            // 添加当前按钮的 active 类
            btn.classList.add('active');
            btn.setAttribute('aria-pressed', 'true');

            // 更新筛选条件并重新渲染
            currentFilter = btn.dataset.filter;
            renderTasks();
        });
    });
}

// 跳转到任务详情页
function goToTaskDetail(taskId) {
    window.location.href = `${projectPage}/task/${encodeURIComponent(taskId)}`;
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

// 显示错误信息
function showError(message) {
    const taskList = document.getElementById('taskList');
    taskList.innerHTML = `<div class="error">${escapeHtml(message)}</div>`;
}

// 启动自动刷新（每 5 秒）
function startAutoRefresh() {
    autoRefreshInterval = setInterval(() => {
        loadTasks();
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
        loadTasks(); // 立即刷新一次
    }
});
