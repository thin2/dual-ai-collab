document.addEventListener('DOMContentLoaded', () => {
    const panels = Object.fromEntries(['progress', 'batch', 'graph', 'history', 'specs']
        .map(name => [name, document.getElementById(name + 'Panel')]));

    const STATUS_ORDER = ['DONE', 'VERIFIED', 'AWAITING_INTEGRATION', 'AWAITING_REVIEW', 'IN_PROGRESS',
        'OPEN', 'PENDING', 'BLOCKED', 'FAILED', 'REJECTED'];
    const STATUS_TEXT = {
        DONE: '已完成', VERIFIED: '已验证', AWAITING_INTEGRATION: '待确认集成', AWAITING_REVIEW: '待审查',
        IN_PROGRESS: '进行中', OPEN: '待办', PENDING: '待处理', BLOCKED: '阻塞', FAILED: '失败', REJECTED: '已拒绝',
    };
    const PHASE_TEXT = { planning: '规划中', developing: '开发中', reviewing: '审查中', completed: '已完成' };
    const RESULT_TEXT = { success: '完成', failed: '失败', running: '进行中', interrupted: '中断' };
    const NODE = { width: 200, height: 92, gapX: 64, gapY: 18 };
    const HISTORY_LIMIT = 10;

    let round = 0;
    let selectedSpec = null;
    let loadedSpec = null;
    const shown = {};

    const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[char]));
    const taskUrl = id => `${projectPage}/task/${encodeURIComponent(id)}`;
    const failure = (what, error) => `<div class="error">${what}加载失败：${escapeHtml(error.message)}</div>`;

    // Rebuilding an unchanged panel on every refresh would drop text selection and scroll position.
    function show(name, html) {
        if (shown[name] !== html) {
            shown[name] = html;
            panels[name].innerHTML = html;
        }
    }

    async function load(path) {
        const response = await fetch(projectApi + path);
        const data = await response.json();
        if (!response.ok || !data.success) throw new Error(data.error || '未知错误');
        return data;
    }

    // A finished task counts as done only once its integration is confirmed.
    function displayStatus(row) {
        if (row.status === 'DONE' && row.integration !== 'confirmed') return 'AWAITING_INTEGRATION';
        return row.status === 'TODO' ? 'OPEN' : row.status;
    }

    function formatTime(value) {
        const date = new Date(value);
        if (!value || Number.isNaN(date.getTime())) return value || '未知';
        return date.toLocaleString('zh-CN', {
            year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false,
        });
    }

    function formatDuration(seconds) {
        if (typeof seconds !== 'number' || !Number.isFinite(seconds)) return '—';
        const total = Math.round(seconds);
        if (total < 60) return `${total} 秒`;
        if (total < 3600) return `${Math.floor(total / 60)} 分 ${total % 60} 秒`;
        return `${Math.floor(total / 3600)} 小时 ${Math.floor(total % 3600 / 60)} 分`;
    }

    function renderProgress(board, checkpoint) {
        const { rows, stats } = board;
        const counts = new Map();
        rows.forEach(row => counts.set(displayStatus(row), (counts.get(displayStatus(row)) || 0) + 1));
        const statuses = [...STATUS_ORDER.filter(status => counts.has(status)),
            ...[...counts.keys()].filter(status => !STATUS_ORDER.includes(status))];
        const label = status => STATUS_TEXT[status] || status;

        const current = checkpoint?.current_task;
        const currentHtml = !current ? '无'
            : rows.some(row => row.id === current) ? `<a href="${taskUrl(current)}">#${escapeHtml(current)}</a>`
                : `#${escapeHtml(current)}`;
        const facts = `
            <dl class="progress-facts">
                <div><dt>当前阶段</dt><dd>${escapeHtml(checkpoint ? PHASE_TEXT[checkpoint.phase] || checkpoint.phase || '未记录' : '未记录')}</dd></div>
                <div><dt>当前任务</dt><dd>${currentHtml}</dd></div>
                <div><dt>阶段记录时间</dt><dd>${escapeHtml(checkpoint?.timestamp ? formatTime(checkpoint.timestamp) : '未记录')}</dd></div>
            </dl>`;

        if (stats.total === 0) {
            return `<div class="progress-head">${facts}</div><div class="empty-state">任务板还是空的。</div>`;
        }
        return `
            <div class="progress-head">
                <div class="progress-figure">
                    <span class="progress-rate">${escapeHtml(stats.completion_rate)}%</span>
                    <span class="progress-caption">${stats.total} 个任务，已完成 ${stats.completed} 个</span>
                </div>
                ${facts}
            </div>
            <div class="progress-bar" role="img" aria-label="${escapeHtml(statuses.map(status => `${label(status)} ${counts.get(status)}`).join('，'))}">
                ${statuses.map(status => `<span class="progress-segment tone-${escapeHtml(status)}" style="width: ${counts.get(status) / stats.total * 100}%" title="${escapeHtml(label(status))} ${counts.get(status)}"></span>`).join('')}
            </div>
            <ul class="status-legend">
                ${statuses.map(status => `<li><span class="task-status ${escapeHtml(status)}">${escapeHtml(label(status))}</span><span class="legend-count">${counts.get(status)}</span></li>`).join('')}
            </ul>
            <p class="panel-note">完成以集成确认为准：做完但还没确认集成的任务算“待确认集成”。</p>`;
    }

    function renderGraph(graph) {
        const { nodes, edges, missing } = graph;
        if (nodes.length === 0) return '<div class="empty-state">任务板还是空的。</div>';

        const byId = new Map(nodes.map(node => [node.id, node]));
        const sources = new Map(nodes.map(node => [node.id, []]));
        edges.forEach(edge => sources.get(edge.to)?.push(edge.from));

        // A task sits one column to the right of its deepest dependency.
        const depth = new Map();
        const depthOf = (id, trail) => {
            if (depth.has(id)) return depth.get(id);
            if (trail.has(id)) return 0; // dependency cycle: stop instead of recursing forever
            trail.add(id);
            const value = sources.get(id).reduce((deepest, source) => Math.max(deepest, depthOf(source, trail) + 1), 0);
            trail.delete(id);
            depth.set(id, value);
            return value;
        };
        nodes.forEach(node => depthOf(node.id, new Set()));

        const columns = [];
        nodes.forEach(node => (columns[depth.get(node.id)] ||= []).push(node));
        const filled = columns.filter(Boolean);
        const tallest = Math.max(...filled.map(column => column.length));
        const place = new Map();
        filled.forEach((column, index) => {
            // Ordering a column by where its dependencies sit keeps the arrows from crossing more than needed.
            const anchor = node => {
                const placed = sources.get(node.id).map(id => place.get(id)).filter(Boolean);
                return placed.length ? placed.reduce((sum, spot) => sum + spot.y, 0) / placed.length : Infinity;
            };
            if (index) column.sort((a, b) => anchor(a) - anchor(b) || nodes.indexOf(a) - nodes.indexOf(b));
            const offset = (tallest - column.length) * (NODE.height + NODE.gapY) / 2;
            column.forEach((node, row) => place.set(node.id, {
                x: index * (NODE.width + NODE.gapX), y: offset + row * (NODE.height + NODE.gapY),
            }));
        });
        const width = filled.length * (NODE.width + NODE.gapX) - NODE.gapX;
        // Leave room below the last row for a cycle's return arrow.
        const height = tallest * (NODE.height + NODE.gapY) - NODE.gapY + 40;

        const paths = edges.filter(edge => place.has(edge.from) && place.has(edge.to)).map(edge => {
            const from = place.get(edge.from);
            const to = place.get(edge.to);
            const pending = byId.get(edge.from).integration !== 'confirmed';
            let line;
            if (to.x > from.x) {
                const x1 = from.x + NODE.width;
                const y1 = from.y + NODE.height / 2;
                const x2 = to.x - 7;
                const y2 = to.y + NODE.height / 2;
                const bend = Math.max(30, (x2 - x1) / 2);
                line = `M ${x1} ${y1} C ${x1 + bend} ${y1}, ${x2 - bend} ${y2}, ${x2} ${y2}`;
            } else {
                // Only a dependency cycle points backwards; route it under the boxes instead of through them.
                const x1 = from.x + NODE.width / 2;
                const y1 = from.y + NODE.height;
                const x2 = to.x + NODE.width / 2;
                const y2 = to.y + NODE.height + 7;
                line = `M ${x1} ${y1} C ${x1} ${y1 + 44}, ${x2} ${y2 + 44}, ${x2} ${y2}`;
            }
            return `<path class="graph-edge${pending ? ' pending' : ''}" marker-end="url(#${pending ? 'arrowPending' : 'arrowDone'})" d="${line}"/>`;
        }).join('');

        const boxes = nodes.map(node => {
            const status = displayStatus(node);
            const spot = place.get(node.id);
            return `
                <a class="graph-node tone-${escapeHtml(status)}" href="${taskUrl(node.id)}" style="left: ${spot.x}px; top: ${spot.y}px" title="${escapeHtml(node.title)}">
                    <span class="graph-node-head">
                        <span class="graph-id">#${escapeHtml(node.id)}</span>
                        <span class="task-status ${escapeHtml(status)}">${escapeHtml(STATUS_TEXT[status] || status)}</span>
                    </span>
                    <span class="graph-title">${escapeHtml(node.title)}</span>
                </a>`;
        }).join('');

        const missingHtml = missing.length ? `
            <ul class="graph-missing">
                ${missing.map(item => `<li>任务 #${escapeHtml(item.task)} 依赖的 #${escapeHtml(item.dependency)} 不在任务板里</li>`).join('')}
            </ul>` : '';

        return `
            <div class="graph-scroll">
                <div class="graph-canvas" style="width: ${width}px; height: ${height}px">
                    <svg class="graph-edges" width="${width}" height="${height}" aria-hidden="true">
                        <defs>
                            <marker id="arrowDone" class="graph-arrow" viewBox="0 0 8 8" refX="1" refY="4" markerWidth="8" markerHeight="8" orient="auto"><path d="M 0 0 L 8 4 L 0 8 z"/></marker>
                            <marker id="arrowPending" class="graph-arrow pending" viewBox="0 0 8 8" refX="1" refY="4" markerWidth="8" markerHeight="8" orient="auto"><path d="M 0 0 L 8 4 L 0 8 z"/></marker>
                        </defs>
                        ${paths}
                    </svg>
                    ${boxes}
                </div>
            </div>
            ${missingHtml}
            <p class="panel-note">箭头从被依赖的任务指向依赖它的任务。虚线表示前一个任务还没确认集成，后一个任务还不能开始。${width > panels.graph.clientWidth ? '图比较宽，可以左右滑动查看。' : ''}</p>`;
    }

    function renderHistory(history, titles) {
        if (history.length === 0) return '<div class="empty-state">还没有执行记录。</div>';
        const rows = history.slice(0, HISTORY_LIMIT).map(record => {
            const title = record.title || titles.get(record.task_id) || '';
            const tone = record.status === 'success' ? 'audit-ok' : record.status === 'running' ? '' : 'audit-mismatch';
            return `
                <tr class="${tone}">
                    <td class="history-task"><a href="${taskUrl(record.task_id)}">#${escapeHtml(record.task_id)}</a> ${escapeHtml(title)}</td>
                    <td>${escapeHtml(record.droid === 'current-session' ? '当前会话' : record.droid || '—')}</td>
                    <td>${escapeHtml(record.model || '—')}</td>
                    <td class="history-nowrap">${escapeHtml(formatTime(record.start_time))}</td>
                    <td class="history-nowrap">${escapeHtml(formatDuration(record.duration_seconds))}</td>
                    <td class="audit-status">${escapeHtml(RESULT_TEXT[record.status] || record.status || '未知')}</td>
                </tr>`;
        }).join('');
        return `
            <div class="audit-table"><table>
                <thead><tr><th>任务</th><th>执行者</th><th>模型</th><th>开始时间</th><th>耗时</th><th>结果</th></tr></thead>
                <tbody>${rows}</tbody>
            </table></div>
            <p class="panel-note">${history.length > HISTORY_LIMIT ? `共 ${history.length} 条，显示最近 ${HISTORY_LIMIT} 条。` : ''}“结果”是这次执行自己的结束方式；任务有没有验收通过，看任务状态。</p>`;
    }

    function renderSpecs(specs, current) {
        if (specs.length === 0) {
            return '<div class="empty-state">还没有规划文档。规划阶段会把规格保存到 planning/specs/。</div>';
        }
        const list = specs.map(spec => `
            <button type="button" class="spec-item${spec.name === selectedSpec ? ' active' : ''}" data-spec="${escapeHtml(spec.name)}" aria-pressed="${spec.name === selectedSpec}">
                <span class="spec-item-title">${escapeHtml(spec.title)}</span>
                <span class="spec-item-meta">${escapeHtml(spec.name)}</span>
                <span class="spec-item-meta">更新于 ${escapeHtml(formatTime(spec.modified))}${spec.name === current ? ' · <span class="spec-badge">当前规格</span>' : ''}</span>
            </button>`).join('');
        let body = '<div class="loading">加载文档中…</div>';
        if (loadedSpec?.name === selectedSpec) {
            body = loadedSpec.error ? failure('文档', loadedSpec.error) : `
                <div class="spec-document-head">
                    <span>planning/specs/${escapeHtml(loadedSpec.spec.name)}</span>
                    <span>更新于 ${escapeHtml(formatTime(loadedSpec.spec.modified))}</span>
                </div>
                ${loadedSpec.spec.truncated ? '<p class="panel-note">文档太长，只显示了开头的 1 MB。</p>' : ''}
                <div class="description">${renderMarkdown(loadedSpec.spec.content)}</div>`;
        }
        return `<div class="spec-layout"><div class="spec-list">${list}</div><article class="spec-document">${body}</article></div>`;
    }

    async function refreshSpecs(specs, current) {
        if (!specs.some(spec => spec.name === selectedSpec)) {
            selectedSpec = specs.some(spec => spec.name === current) ? current : specs[0]?.name ?? null;
        }
        const chosen = specs.find(spec => spec.name === selectedSpec);
        if (chosen && (loadedSpec?.name !== chosen.name || loadedSpec.modified !== chosen.modified)) {
            show('specs', renderSpecs(specs, current));
            const name = chosen.name;
            let result;
            try {
                result = { name, modified: chosen.modified, spec: (await load('/specs/' + encodeURIComponent(name))).spec };
            } catch (error) {
                result = { name, modified: chosen.modified, error };
            }
            if (selectedSpec !== name) return; // another document was picked while this one loaded
            loadedSpec = result;
        }
        show('specs', renderSpecs(specs, current));
    }

    let lastSpecs = null;
    async function refresh() {
        const mine = ++round;
        const [board, checkpoint, graph, batch, history, specs] = await Promise.allSettled(
            ['/board', '/checkpoint', '/graph', '/batch', '/history', '/specs'].map(load));
        if (mine !== round) return;
        const failed = (...results) => results.find(result => result.status === 'rejected');

        show('progress', failed(board, checkpoint) ? failure('进度', failed(board, checkpoint).reason)
            : renderProgress(board.value, checkpoint.value.checkpoint));
        show('batch', failed(batch) ? failure('批次预览', batch.reason) : renderBatchPreview(batch.value));
        show('graph', failed(graph) ? failure('依赖图', graph.reason) : renderGraph(graph.value));
        const titles = new Map(failed(graph) ? [] : graph.value.nodes.map(node => [node.id, node.title]));
        show('history', failed(history) ? failure('执行记录', history.reason) : renderHistory(history.value.history, titles));
        if (failed(specs)) {
            lastSpecs = null;
            show('specs', failure('规划文档', specs.reason));
        } else {
            lastSpecs = { specs: specs.value.specs, current: failed(checkpoint) ? null : checkpoint.value.checkpoint?.spec };
            await refreshSpecs(lastSpecs.specs, lastSpecs.current);
        }
    }

    panels.specs.addEventListener('click', event => {
        const button = event.target.closest('[data-spec]');
        if (!button || !lastSpecs || button.dataset.spec === selectedSpec) return;
        selectedSpec = button.dataset.spec;
        refreshSpecs(lastSpecs.specs, lastSpecs.current);
    });

    let timer = null;
    function schedule() {
        if (timer) clearInterval(timer);
        timer = document.hidden ? null : setInterval(refresh, 5000);
    }
    refresh();
    schedule();
    document.addEventListener('visibilitychange', () => {
        schedule();
        if (!document.hidden) refresh();
    });
});
