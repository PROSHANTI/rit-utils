(() => {
    'use strict';
    function element(tag, text, className) {
        const node = document.createElement(tag);
        if (text !== undefined) node.textContent = text;
        if (className) node.className = className;
        return node;
    }
    function reset(dialog) {
        const panel = dialog.querySelector('#import-preview');
        panel.hidden = true;
        panel.replaceChildren();
        dialog.classList.remove('has-preview');
        dialog.querySelector('.import-error').textContent = '';
        const button = dialog.querySelector('#import-submit');
        button.textContent = 'Проверить файл';
        button.disabled = false;
    }
    function setBusy(dialog, value) {
        dialog.dataset.busy = String(value);
        dialog.setAttribute('aria-busy', String(value));
        dialog.querySelectorAll('button, input').forEach(control => { control.disabled = value; });
    }
    function render(dialog, {rows, summary, valid, alreadyImported = false}) {
        const panel = dialog.querySelector('#import-preview');
        const errors = rows.filter(row => row.error).length;
        panel.replaceChildren(element('p', errors ? 'Строк с ошибками: ' + errors + '.' : summary, 'import-summary'));
        const scroll = element('div', undefined, 'import-preview-scroll');
        const table = element('table', undefined, 'import-preview-table');
        const head = table.createTHead().insertRow();
        ['Строка', 'Артикул', 'Наименование', 'В файле, шт.', 'Было → станет', 'Результат'].forEach(text => head.appendChild(element('th', text)));
        const body = table.createTBody();
        rows.forEach(item => {
            const row = body.insertRow();
            row.classList.toggle('import-invalid', Boolean(item.error));
            const name = [item.name, ...(item.details || [])].filter(Boolean).join('\n');
            const after = item.error || alreadyImported ? '—' : String(item.before ?? 0) + ' → ' + item.after;
            [item.row, item.article || '—', name, item.quantity, after, item.error || item.result].forEach(value => {
                row.appendChild(element('td', value ?? '—'));
            });
        });
        scroll.appendChild(table);
        panel.appendChild(scroll);
        panel.hidden = false;
        dialog.classList.add('has-preview');
        dialog.querySelector('.import-error').textContent = errors
            ? 'Исправьте подсвеченные строки в Excel и выберите файл заново.' : '';
        const canImport = valid && !errors && !alreadyImported;
        const button = dialog.querySelector('#import-submit');
        button.textContent = 'Импортировать';
        button.disabled = !canImport;
        return canImport;
    }
    window.ExcelImportDialog = {reset, render, setBusy};
})();
