// Renders the Markdown subset found in task text: headings, lists, code, quotes, tables,
// bold and links. All text is HTML-escaped before any tag is added, so task content
// cannot inject markup.
const renderMarkdown = (() => {
    const escapeText = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[char]));

    const FENCE = /^\s*(```|~~~)/;
    const HEADING = /^\s{0,3}(#{1,6})\s+(.*?)(?:\s+#+)?\s*$/;
    const RULE = /^\s{0,3}([-*_])(?:\s*\1){2,}\s*$/;
    const QUOTE = /^\s{0,3}>\s?/;
    const ITEM = /^(\s*)([-*+]|\d{1,9}[.)])\s+(.*)$/;
    const TABLE_ROW = /^\s*\|.*\|\s*$/;
    const TABLE_RULE = /^\s*\|?\s*:?-+:?\s*(?:\|\s*:?-+:?\s*)*\|?\s*$/;

    function inline(text) {
        // Code spans are split out first so their content is never read as bold or a link.
        return String(text).split(/(`[^`\n]+`)/g).map((part, index) => {
            if (index % 2) return `<code>${escapeText(part.slice(1, -1))}</code>`;
            return escapeText(part)
                .replace(/\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>')
                .replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>');
        }).join('');
    }

    function isTable(lines, i) {
        return TABLE_ROW.test(lines[i]) && i + 1 < lines.length && lines[i + 1].includes('|') && TABLE_RULE.test(lines[i + 1]);
    }

    function startsBlock(lines, i) {
        const line = lines[i];
        return FENCE.test(line) || HEADING.test(line) || RULE.test(line) || QUOTE.test(line) || ITEM.test(line) || isTable(lines, i);
    }

    function cells(row) {
        return row.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map(cell => cell.trim());
    }

    // Items arrive in document order; an item indented deeper than the first one of its
    // level belongs to the item before it.
    function listHtml(items) {
        const base = items[0].indent;
        let html = '';
        let index = 0;
        while (index < items.length) {
            const ordered = items[index].ordered;
            const start = items[index].number;
            let body = '';
            while (index < items.length && items[index].ordered === ordered) {
                const item = items[index++];
                const children = [];
                while (index < items.length && items[index].indent > base + 1) children.push(items[index++]);
                const task = /^\[([ xX])\]\s+(.*)$/.exec(item.lines[0]);
                const lines = task ? [task[2], ...item.lines.slice(1)] : item.lines;
                const box = task ? `<input type="checkbox" disabled${task[1] === ' ' ? '' : ' checked'}> ` : '';
                body += `<li${task ? ' class="md-task"' : ''}>${box}${lines.map(inline).join('<br>')}${children.length ? listHtml(children) : ''}</li>`;
            }
            html += ordered ? `<ol${start === 1 ? '' : ` start="${start}"`}>${body}</ol>` : `<ul>${body}</ul>`;
        }
        return html;
    }

    function render(source) {
        const lines = String(source ?? '').replace(/\r\n?/g, '\n').split('\n');
        const html = [];
        let i = 0;
        while (i < lines.length) {
            const line = lines[i];
            if (!line.trim()) {
                i++;
                continue;
            }
            const fence = FENCE.exec(line);
            if (fence) {
                const code = [];
                i++;
                while (i < lines.length && !lines[i].trim().startsWith(fence[1])) code.push(lines[i++]);
                i++;
                html.push(`<pre><code>${escapeText(code.join('\n'))}</code></pre>`);
                continue;
            }
            const heading = HEADING.exec(line);
            if (heading) {
                // Section titles on the page are h3, so headings inside the text start at h4.
                const level = heading[1].length;
                const tag = `h${Math.min(level + 3, 6)}`;
                html.push(`<${tag} class="md-h${level}">${inline(heading[2])}</${tag}>`);
                i++;
                continue;
            }
            if (RULE.test(line)) {
                html.push('<hr>');
                i++;
                continue;
            }
            if (QUOTE.test(line)) {
                const quoted = [];
                while (i < lines.length && QUOTE.test(lines[i])) quoted.push(lines[i++].replace(QUOTE, ''));
                html.push(`<blockquote>${render(quoted.join('\n'))}</blockquote>`);
                continue;
            }
            if (isTable(lines, i)) {
                const head = cells(line);
                const rows = [];
                i += 2;
                while (i < lines.length && TABLE_ROW.test(lines[i])) rows.push(cells(lines[i++]));
                const headHtml = head.map(cell => `<th>${inline(cell)}</th>`).join('');
                const bodyHtml = rows.map(row => `<tr>${head.map((_, n) => `<td>${inline(row[n] ?? '')}</td>`).join('')}</tr>`).join('');
                html.push(`<div class="md-table"><table><thead><tr>${headHtml}</tr></thead><tbody>${bodyHtml}</tbody></table></div>`);
                continue;
            }
            if (ITEM.test(line)) {
                const items = [];
                while (i < lines.length) {
                    const match = ITEM.exec(lines[i]);
                    if (match) {
                        const ordered = /\d/.test(match[2]);
                        items.push({
                            indent: match[1].replace(/\t/g, '    ').length,
                            ordered,
                            number: ordered ? parseInt(match[2], 10) : 1,
                            lines: [match[3]],
                        });
                    } else if (lines[i].trim() && /^\s/.test(lines[i])) {
                        items[items.length - 1].lines.push(lines[i].trim());
                    } else if (!(!lines[i].trim() && i + 1 < lines.length && ITEM.test(lines[i + 1]))) {
                        break;
                    }
                    i++;
                }
                html.push(listHtml(items));
                continue;
            }
            const paragraph = [];
            while (i < lines.length && lines[i].trim() && !(paragraph.length && startsBlock(lines, i))) {
                paragraph.push(lines[i++].trim());
            }
            html.push(`<p>${paragraph.map(inline).join('<br>')}</p>`);
        }
        return html.join('');
    }

    return render;
})();
