// Next-batch preview shared by the team and overview pages.
function renderBatchPreview(data) {
    const escapeText = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[char]));
    const batch = data.batch || [];
    const skipped = data.skipped || [];

    if (batch.length === 0 && skipped.length === 0) {
        return '<div class="empty-state">当前没有可执行的任务。所有任务可能已完成、被阻塞或依赖未满足。</div>';
    }

    let html = '';
    if (batch.length > 0) {
        html += '<div class="batch-list"><h3 class="batch-subtitle">计划执行任务</h3>';
        for (const task of batch) {
            const files = task.files && task.files.length > 0
                ? `<span class="batch-files">${task.files.length} 个文件</span>`
                : '';
            html += `
                <div class="batch-item">
                    <div class="batch-header">
                        <span class="batch-task-id">${escapeText(task.task_id)}</span>
                        <span class="batch-title">${escapeText(task.task_title)}</span>
                    </div>
                    <div class="batch-details">
                        ${task.role ? `<span>角色: ${escapeText(task.role)}</span>
                        <span>Droid: ${escapeText(task.droid || '未配置')}</span>
                        <span>模型: ${escapeText(task.model || '未配置')}</span>` : '<span>当前会话直接执行</span>'}
                        <span>复杂度: ${escapeText(task.complexity || '未知')}</span>
                        ${files}
                    </div>
                </div>
            `;
        }
        html += '</div>';
    }
    if (skipped.length > 0) {
        html += '<div class="skipped-list"><h3 class="batch-subtitle">跳过任务</h3>';
        for (const item of skipped) {
            html += `
                <div class="skipped-item">
                    <span class="skipped-id">${escapeText(item.id)}</span>
                    <span class="skipped-reason">${escapeText(item.reason)}</span>
                </div>
            `;
        }
        html += '</div>';
    }
    return html;
}
