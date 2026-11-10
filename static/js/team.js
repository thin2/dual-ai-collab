document.addEventListener('DOMContentLoaded', () => {
    const rolesPanel = document.getElementById('rolesPanel');
    const checksPanel = document.getElementById('checksPanel');
    const auditPanel = document.getElementById('auditPanel');
    const batchPanel = document.getElementById('batchPanel');
    const checkButton = document.getElementById('checkButton');

    let refreshInterval = null;
    const versions = { roles: 0, audit: 0, batch: 0 };

    // Escape HTML to prevent XSS
    function escapeHtml(text) {
        if (text == null) return '';
        const div = document.createElement('div');
        div.textContent = String(text);
        return div.innerHTML;
    }

    // Load roles configuration
    async function loadRoles() {
        const version = ++versions.roles;
        try {
            const response = await fetch(projectApi + '/team');
            const data = await response.json();
            if (version !== versions.roles) return;
            
            if (!response.ok || !data.success) {
                rolesPanel.innerHTML = `<div class="error">加载角色配置失败：${escapeHtml(data.error || '未知错误')}</div>`;
                return;
            }

            const { roles, parallel } = data;
            
            if (!roles || Object.keys(roles).length === 0) {
                rolesPanel.innerHTML = '<div class="empty-state">未配置任何角色。请通过任务管理技能选择模型并配置团队。</div>';
                return;
            }

            let html = '<div class="roles-grid">';
            for (const [role, config] of Object.entries(roles)) {
                const droid = config.droid || '未配置';
                const model = config.model || '未配置';
                const description = config.description || '';
                const readOnly = config.read_only ? ' · 只读' : '';
                
                html += `
                    <div class="role-card">
                        <div class="role-header">
                            <h3 class="role-name">${escapeHtml(role)}</h3>
                            ${readOnly ? '<span class="role-badge">只读</span>' : ''}
                        </div>
                        <div class="role-detail">
                            <span class="detail-label">Droid</span>
                            <span class="detail-value">${escapeHtml(droid)}</span>
                        </div>
                        <div class="role-detail">
                            <span class="detail-label">模型</span>
                            <span class="detail-value">${escapeHtml(model)}</span>
                        </div>
                        ${description ? `<p class="role-description">${escapeHtml(description)}</p>` : ''}
                    </div>
                `;
            }
            html += '</div>';
            
            html += `
                <div class="parallel-config">
                    <span>并行配置：最大并行数 ${parallel.max_parallel}，最大重试次数 ${parallel.max_retries}</span>
                </div>
            `;
            
            rolesPanel.innerHTML = html;
        } catch (error) {
            if (version !== versions.roles) return;
            rolesPanel.innerHTML = `<div class="error">网络错误：${escapeHtml(error.message)}</div>`;
        }
    }

    // Run connection checks
    async function runChecks() {
        checkButton.disabled = true;
        checkButton.textContent = '检查中…';
        checksPanel.innerHTML = '<div class="loading">正在检查连接…</div>';
        
        try {
            const response = await fetch(projectApi + '/team/check');
            const data = await response.json();
            
            if (!response.ok || !data.success) {
                checksPanel.innerHTML = `<div class="error">检查失败：${escapeHtml(data.error || '未知错误')}</div>`;
                return;
            }

            const { checks } = data;
            
            if (!checks || checks.length === 0) {
                checksPanel.innerHTML = '<div class="empty-state">没有需要检查的角色配置。</div>';
                return;
            }

            let html = '<div class="checks-list">';
            for (const check of checks) {
                const statusClass = check.ok ? 'check-ok' : 'check-fail';
                const statusText = check.ok ? '✓ 连接成功' : '✗ 连接失败';
                const problems = check.problems && check.problems.length > 0
                    ? check.problems.map(p => `<li>${escapeHtml(p)}</li>`).join('')
                    : '';
                
                html += `
                    <div class="check-item ${statusClass}">
                        <div class="check-header">
                            <h3 class="check-role">${escapeHtml(check.role)}</h3>
                            <span class="check-status">${statusText}</span>
                        </div>
                        <div class="check-config">
                            <span>Droid: ${escapeHtml(check.droid || '未配置')}</span>
                            <span>模型: ${escapeHtml(check.model || '未配置')}</span>
                        </div>
                        ${problems ? `<ul class="check-problems">${problems}</ul>` : ''}
                    </div>
                `;
            }
            html += '</div>';
            
            checksPanel.innerHTML = html;
        } catch (error) {
            checksPanel.innerHTML = `<div class="error">网络错误：${escapeHtml(error.message)}</div>`;
        } finally {
            checkButton.disabled = false;
            checkButton.textContent = '运行检查';
        }
    }

    // Load audit records
    async function loadAudit() {
        const version = ++versions.audit;
        try {
            const response = await fetch(projectApi + '/team/audit');
            const data = await response.json();
            if (version !== versions.audit) return;
            
            if (!response.ok || !data.success) {
                auditPanel.innerHTML = `<div class="error">加载核对记录失败：${escapeHtml(data.error || '未知错误')}</div>`;
                return;
            }

            const { records } = data;
            
            if (!records || records.length === 0) {
                auditPanel.innerHTML = '<div class="empty-state">尚未核对：没有可用的执行记录，暂时无法确认实际使用的模型。</div>';
                return;
            }

            let html = '<div class="audit-table"><table><thead><tr><th>会话</th><th>任务</th><th>角色</th><th>预期模型</th><th>实际模型</th><th>状态</th></tr></thead><tbody>';
            for (const record of records) {
                const statusClass = record.ok ? 'audit-ok' : 'audit-mismatch';
                const statusText = record.ok ? '✓ 一致' : '✗ 不一致';
                
                html += `
                    <tr class="${statusClass}">
                        <td class="audit-session">${escapeHtml(record.session_id)}</td>
                        <td class="audit-title">${escapeHtml(record.title)}</td>
                        <td>${escapeHtml(record.role)}</td>
                        <td>${escapeHtml(record.expected || '未配置')}</td>
                        <td>${escapeHtml(record.actual || '未知')}</td>
                        <td class="audit-status">${statusText}</td>
                    </tr>
                `;
            }
            html += '</tbody></table></div>';
            
            auditPanel.innerHTML = html;
        } catch (error) {
            if (version !== versions.audit) return;
            auditPanel.innerHTML = `<div class="error">网络错误：${escapeHtml(error.message)}</div>`;
        }
    }

    // Load batch preview
    async function loadBatch() {
        const version = ++versions.batch;
        try {
            const response = await fetch(projectApi + '/batch');
            const data = await response.json();
            if (version !== versions.batch) return;
            
            if (!response.ok || !data.success) {
                batchPanel.innerHTML = `<div class="error">加载批次预览失败：${escapeHtml(data.error || '未知错误')}</div>`;
                return;
            }

            const { batch, skipped } = data;
            
            if ((!batch || batch.length === 0) && (!skipped || skipped.length === 0)) {
                batchPanel.innerHTML = '<div class="empty-state">当前没有可执行的任务。所有任务可能已完成、被阻塞或依赖未满足。</div>';
                return;
            }

            let html = '';
            
            if (batch && batch.length > 0) {
                html += '<div class="batch-list"><h3 class="batch-subtitle">计划执行任务</h3>';
                for (const task of batch) {
                    const files = task.files && task.files.length > 0
                        ? `<span class="batch-files">${task.files.length} 个文件</span>`
                        : '';
                    
                    html += `
                        <div class="batch-item">
                            <div class="batch-header">
                                <span class="batch-task-id">${escapeHtml(task.task_id)}</span>
                                <span class="batch-title">${escapeHtml(task.task_title)}</span>
                            </div>
                            <div class="batch-details">
                                <span>角色: ${escapeHtml(task.role)}</span>
                                <span>Droid: ${escapeHtml(task.droid || '未配置')}</span>
                                <span>模型: ${escapeHtml(task.model || '未配置')}</span>
                                <span>复杂度: ${escapeHtml(task.complexity || '未知')}</span>
                                ${files}
                            </div>
                        </div>
                    `;
                }
                html += '</div>';
            }
            
            if (skipped && skipped.length > 0) {
                html += '<div class="skipped-list"><h3 class="batch-subtitle">跳过任务</h3>';
                for (const item of skipped) {
                    html += `
                        <div class="skipped-item">
                            <span class="skipped-id">${escapeHtml(item.id)}</span>
                            <span class="skipped-reason">${escapeHtml(item.reason)}</span>
                        </div>
                    `;
                }
                html += '</div>';
            }
            
            batchPanel.innerHTML = html;
        } catch (error) {
            if (version !== versions.batch) return;
            batchPanel.innerHTML = `<div class="error">网络错误：${escapeHtml(error.message)}</div>`;
        }
    }

    // Refresh data (excluding checks which are manual)
    function refreshData() {
        loadRoles();
        loadAudit();
        loadBatch();
    }

    // Initial load
    refreshData();

    // Auto-refresh every 5 seconds
    function startRefresh() {
        if (refreshInterval) clearInterval(refreshInterval);
        refreshInterval = document.hidden ? null : setInterval(refreshData, 5000);
    }
    startRefresh();
    document.addEventListener('visibilitychange', () => {
        startRefresh();
        if (!document.hidden) refreshData();
    });

    // Manual check button
    checkButton.addEventListener('click', runChecks);
});
