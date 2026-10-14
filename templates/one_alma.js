(() => {
    const container = document.querySelector('.inventory-container');
    const inputs = [...container.querySelectorAll('input[data-unit-id]')];
    const status = document.getElementById('save-status');
    const download = container.querySelector('.download-pdf');
    const tableBody = container.querySelector('.inventory-table tbody');
    const selections = [...container.querySelectorAll('.select-product')];
    const selectAll = document.getElementById('select-all');
    const deleteSelected = document.getElementById('delete-selected');
    const productDialog = document.getElementById('product-dialog');
    const productForm = document.getElementById('product-form');
    const importDialog = document.getElementById('import-dialog');
    const importForm = document.getElementById('import-form');
    const csrfToken = container.dataset.csrfToken;
    const params = new URLSearchParams(window.location.search);
    const requestedSort = Number(params.get('sort') || 0);
    let sortColumn = Number.isInteger(requestedSort) && requestedSort >= 0 && requestedSort <= 8 ? requestedSort : 0;
    let descending = params.get('descending') === 'true';
    const collator = new Intl.Collator('ru', {numeric: true, sensitivity: 'base'});

    async function refreshSession() {
        return fetch('/refresh', {method: 'POST', credentials: 'same-origin', headers: {'Accept': 'application/json'}});
    }

    async function api(url, options) {
        const settings = {...options, credentials: 'same-origin', headers: {'Accept': 'application/json'}};
        let response = await fetch(url, settings);
        if (response.status === 401) {
            await refreshSession();
            response = await fetch(url, settings);
        }
        if (response.status === 401 || response.redirected) {
            window.location.href = '/';
            throw new Error('Войдите в систему и повторите действие.');
        }
        if (!response.headers.get('content-type')?.includes('application/json')) {
            throw new Error('Сервер не смог выполнить действие. Попробуйте позже.');
        }
        const data = await response.json();
        if (!response.ok) {
            throw new Error(typeof data.detail === 'string' ? data.detail : 'Проверьте поля формы и повторите действие.');
        }
        return data;
    }

    function errorMessage(error) {
        return error instanceof TypeError ? 'Нет связи с сервером. Повторите действие.' : error.message;
    }

    function updateSelection() {
        const selected = selections.filter(input => input.checked).length;
        document.getElementById('selection-count').textContent = `Выбрано: ${selected}`;
        deleteSelected.disabled = selected === 0;
        selectAll.checked = selected > 0 && selected === selections.length;
        selectAll.indeterminate = selected > 0 && selected < selections.length;
    }

    function setBusy(busy) {
        container.querySelectorAll('button, input').forEach(control => { control.disabled = busy; });
        download.setAttribute('aria-disabled', String(busy));
        if (!busy) updateSelection();
    }

    function sortValue(row, column) {
        const cells = JSON.parse(row.dataset.cells);
        if (column === 8) return Number(row.dataset.sold);
        const text = cells[column];
        if (text === '' || text === '—') return null;
        if ([0, 5, 6, 7].includes(column)) return Number(text.replaceAll(' ', '').replace(',', '.'));
        if (column === 4) {
            const [month, year] = text.split('.');
            return Number(year) * 12 + Number(month);
        }
        return text;
    }

    function sortRows() {
        const rows = [...tableBody.querySelectorAll('tr')];
        rows.sort((left, right) => {
            const a = sortValue(left, sortColumn), b = sortValue(right, sortColumn);
            if (a === null || b === null) return a === b ? 0 : a === null ? 1 : -1;
            const difference = typeof a === 'number' ? a - b : collator.compare(a, b);
            return descending ? -difference : difference;
        });
        rows.forEach(row => { tableBody.appendChild(row); });
        container.querySelectorAll('[data-sort-column]').forEach(button => {
            const active = Number(button.dataset.sortColumn) === sortColumn;
            button.closest('th').setAttribute('aria-sort', active ? descending ? 'descending' : 'ascending' : 'none');
            button.querySelector('span').textContent = active ? descending ? '↓' : '↑' : '↕';
        });
        download.href = `/one_alma/pdf?sort=${sortColumn}&descending=${descending}`;
    }

    container.querySelectorAll('[data-sort-column]').forEach(button => {
        button.addEventListener('click', () => {
            const column = Number(button.dataset.sortColumn);
            descending = column === sortColumn ? !descending : false;
            sortColumn = column;
            const url = new URL(window.location.href);
            url.searchParams.set('sort', sortColumn);
            url.searchParams.set('descending', descending);
            window.history.replaceState(null, '', url);
            sortRows();
        });
    });

    for (const input of inputs) {
        input.addEventListener('change', async () => {
            const previous = !input.checked;
            setBusy(true);
            status.classList.remove('error');
            status.textContent = 'Сохраняю…';
            try {
                const data = await api(`/one_alma/units/${input.dataset.unitId}`, {
                    method: 'POST', body: new URLSearchParams({sold: String(input.checked), csrf_token: csrfToken}),
                });
                document.getElementById('total-count').textContent = data.total;
                document.getElementById('sold-count').textContent = data.sold;
                document.getElementById('available-count').textContent = data.available;
                data.valuations.forEach((valuation, index) => {
                    const row = container.querySelector(`[data-valuation-index="${index}"]`);
                    row.querySelectorAll('.valuation-amount').forEach((cell, column) => { cell.textContent = valuation.amounts[column]; });
                    row.querySelectorAll('.unpriced-note').forEach((cell, column) => {
                        cell.textContent = valuation.unpriced[column] ? `Без цены: ${valuation.unpriced[column]} шт.` : '';
                    });
                });
                for (const product of data.products) {
                    const row = container.querySelector(`[data-product-id="${product.id}"]`);
                    // Another tab may have added/removed a row: reload before applying a stale snapshot.
                    if (!row || JSON.stringify(JSON.parse(row.dataset.cells)) !== JSON.stringify(product.cells) ||
                        row.querySelectorAll('[data-unit-id]').length !== product.units.length ||
                        product.units.some(unit => !row.querySelector(`[data-unit-id="${unit.id}"]`))) {
                        window.location.reload();
                        return;
                    }
                    row.dataset.sold = product.sold;
                    row.classList.toggle('sold-out', product.available === 0);
                    row.querySelector('.row-sold').textContent = `Продано: ${product.sold} из ${product.units.length}`;
                    row.querySelector('.row-available').textContent = `В наличии: ${product.available}`;
                    for (const unit of product.units) row.querySelector(`[data-unit-id="${unit.id}"]`).checked = unit.sold;
                }
                if (data.products.length !== tableBody.rows.length) window.location.reload();
                sortRows();
                status.textContent = 'Сохранено.';
            } catch (error) {
                input.checked = previous;
                status.classList.add('error');
                status.textContent = errorMessage(error);
            } finally {
                setBusy(false);
            }
        });
    }

    selectAll.addEventListener('change', () => {
        selections.forEach(input => { input.checked = selectAll.checked; });
        updateSelection();
    });
    selections.forEach(input => { input.addEventListener('change', updateSelection); });

    function openProduct(row = null) {
        productForm.reset();
        productForm.querySelector('.dialog-status').textContent = '';
        productForm.dataset.productId = row?.dataset.productId || '';
        document.getElementById('product-dialog-title').textContent = row ? 'Изменить товар' : 'Добавить товар';
        if (row) {
            const cells = JSON.parse(row.dataset.cells);
            const fields = ['position', 'article', 'name', 'volume', 'expiry', 'central_bank_price', 'wholesale_price', 'market_price'];
            fields.forEach((field, column) => {
                productForm.elements.namedItem(field).value = cells[column] === '—' ? '' : cells[column];
            });
            productForm.elements.namedItem('quantity').value = row.dataset.quantity;
        }
        productDialog.showModal();
    }

    document.getElementById('add-product').addEventListener('click', () => { openProduct(); });
    document.getElementById('import-products').addEventListener('click', () => {
        importForm.reset();
        importForm.querySelector('.dialog-status').textContent = '';
        importDialog.showModal();
    });
    container.querySelectorAll('.close-dialog').forEach(button => {
        button.addEventListener('click', () => { button.closest('dialog').close(); });
    });
    container.querySelectorAll('.edit-product').forEach(button => {
        button.addEventListener('click', () => { openProduct(button.closest('tr')); });
    });

    async function submitForm(form, url, method) {
        const message = form.querySelector('.dialog-status');
        const body = new FormData(form);
        body.set('csrf_token', csrfToken);
        setBusy(true);
        message.textContent = 'Сохраняю…';
        try {
            await api(url, {method, body});
            window.location.reload();
        } catch (error) {
            message.textContent = errorMessage(error);
            setBusy(false);
        }
    }

    productForm.addEventListener('submit', event => {
        event.preventDefault();
        const id = productForm.dataset.productId;
        submitForm(productForm, id ? `/one_alma/products/${id}` : '/one_alma/products', id ? 'PUT' : 'POST');
    });
    importForm.addEventListener('submit', event => {
        event.preventDefault();
        submitForm(importForm, '/one_alma/import', 'POST');
    });

    async function deleteProducts(ids) {
        if (!window.confirm(`Удалить выбранные позиции (${ids.length}) вместе с их отметками продаж?`)) return;
        const body = new URLSearchParams({csrf_token: csrfToken});
        ids.forEach(id => { body.append('product_ids', id); });
        setBusy(true);
        status.textContent = 'Удаляю…';
        status.classList.remove('error');
        try {
            await api('/one_alma/products', {method: 'DELETE', body});
            window.location.reload();
        } catch (error) {
            status.textContent = errorMessage(error);
            status.classList.add('error');
            setBusy(false);
        }
    }

    deleteSelected.addEventListener('click', () => { deleteProducts(selections.filter(input => input.checked).map(input => input.value)); });
    container.querySelectorAll('.delete-product').forEach(button => {
        button.addEventListener('click', () => { deleteProducts([button.closest('tr').dataset.productId]); });
    });
    updateSelection();
    sortRows();
    setInterval(() => { refreshSession().catch(() => {}); }, 10 * 60 * 1000);
})();
