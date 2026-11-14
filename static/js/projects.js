document.addEventListener('DOMContentLoaded', () => {
    const selector = document.getElementById('projectSelect');
    selector.addEventListener('change', () => {
        window.location.href = '/project/' + encodeURIComponent(selector.value) + '/tasks';
    });
    const form = document.getElementById('registerProject');
    const toggle = document.getElementById('registerToggle');
    toggle.addEventListener('click', () => {
        form.hidden = !form.hidden;
        toggle.setAttribute('aria-expanded', String(!form.hidden));
        if (!form.hidden) form.elements.name.focus();
    });
    form.addEventListener('submit', async event => {
        event.preventDefault();
        const button = form.querySelector('button[type="submit"]');
        const message = document.getElementById('projectMessage');
        button.disabled = true;
        message.textContent = '正在检查项目目录…';
        try {
            const response = await fetch('/api/projects', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({name: form.elements.name.value, path: form.elements.path.value})
            });
            const data = await response.json();
            if (!response.ok || !data.success) throw new Error(data.error || '登记失败，请重试');
            window.location.href = '/project/' + encodeURIComponent(data.project.id) + '/tasks';
        } catch (error) {
            message.textContent = error.message;
            button.disabled = false;
        }
    });
});
