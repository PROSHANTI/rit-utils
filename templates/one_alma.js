(() => {
    const container = document.querySelector('.inventory-container');
    const status = document.getElementById('save-status');
    const download = container.querySelector('.download-pdf');
    const tableBody = container.querySelector('.inventory-table tbody');
    const productDialog = document.getElementById('product-dialog');
    const productForm = document.getElementById('product-form');
    const importDialog = document.getElementById('import-dialog');
    const importForm = document.getElementById('import-form');
    let importFingerprint = '';
    let importValid = false;
    const importSubmit = document.getElementById('import-submit');
    const importPreview = document.getElementById('import-preview');
    const csrfToken = container.dataset.csrfToken;
    const countEditor = document.getElementById('count-editor');
    const countForm = document.getElementById('count-form');
    const countInput = document.getElementById('count-quantity');
    const countError = document.getElementById('count-error');
    let countRow = null;
    let countAnchor = null;
    const saleDialog = document.getElementById('sale-dialog');
    const saleForm = document.getElementById('sale-form');
    const saleQuantity = document.getElementById('sale-quantity');
    const salePrice = document.getElementById('sale-price');
    const historyDialog = document.getElementById('history-dialog');
    const undoDialog = document.getElementById('undo-dialog');
    let saleRow = null, historyRow = null, saleRequestId = '', cancelSaleId = null;
    const moscowTime = value => new Intl.DateTimeFormat('ru-RU', {timeZone: 'Europe/Moscow', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23'}).format(value);
    const rubles = cents => cents === null ? '—' : new Intl.NumberFormat('ru-RU', {minimumFractionDigits: 2, maximumFractionDigits: 2}).format(cents / 100) + ' ₽';
    function priceCents(raw) {
        const value = raw.replace(/[ \u00a0]/g, '');
        if (!value || value === '—') return null;
        if (!/^\d{1,9}(?:[.,]\d{1,2})?$/.test(value)) throw new Error('Укажите цену от 0 с точностью до копеек.');
        const [whole, fraction = ''] = value.replace(',', '.').split('.');
        return Number(whole) * 100 + Number(fraction.padEnd(2, '0'));
    }
    let busy = false;
    const params = new URLSearchParams(window.location.search);
    const requestedSort = Number(params.get('sort') || 0);
    let sortColumn = Number.isInteger(requestedSort) && requestedSort >= 0 && requestedSort <= 9 ? requestedSort : 0;
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
            throw new Error('Сессия завершена. Войдите снова. Введённые данные оставлены в форме.');
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

    function setBusy(value) {
        busy = value;
        container.querySelectorAll('button, input').forEach(control => { control.disabled = busy; });
        download.setAttribute('aria-disabled', String(busy));
        if (!busy) {
            tableBody.querySelectorAll('[data-count-kind="showcase"]').forEach(button => {
                const row = button.closest('tr');
                button.disabled = Number(row.dataset.quantity) === Number(row.dataset.sold);
            });
        }
        tableBody.querySelectorAll('.record-sale').forEach(button => {
            const row = button.closest('tr');
            button.disabled = busy || Number(row.dataset.quantity) === Number(row.dataset.sold);
        });
        updateCountControls();
        updateSaleControls();
    }

    function sortValue(row, column) {
        const cells = JSON.parse(row.dataset.cells);
        if (column === 8) return Number(row.dataset.sold);
        if (column === 9) return Number(row.dataset.showcase);
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

    function updateCountControls() {
        const value = Number(countInput.value), maximum = Number(countInput.max);
        const valid = countInput.value !== '' && Number.isInteger(value) && value >= 0 && value <= maximum;
        document.getElementById('count-minus').disabled = busy || value <= 0;
        document.getElementById('count-plus').disabled = busy || value >= maximum;
        document.getElementById('count-save').disabled = busy || !valid;
    }

    function closeCount() {
        if (busy || !countEditor.open) return;
        countEditor.close();
        countRow = null;
        countAnchor?.focus();
        countAnchor = null;
    }

    function openCount(button) {
        countRow = button.closest('tr');
        countAnchor = button;
        const cells = JSON.parse(countRow.dataset.cells);
        const maximum = Number(countRow.dataset.quantity) - Number(countRow.dataset.sold);
        document.getElementById('count-context').textContent = `${cells[1]} · можно выставить до ${maximum} шт.`;
        countInput.max = maximum;
        countInput.value = countRow.dataset.showcase;
        countError.textContent = '';
        updateCountControls();
        countEditor.showModal();
        countInput.focus();
    }

    function applyInventory(data) {
        if (data.products.length !== tableBody.rows.length || data.products.some(product => {
            const row = tableBody.querySelector(`[data-product-id="${product.id}"]`);
            return !row || JSON.stringify(JSON.parse(row.dataset.cells)) !== JSON.stringify(product.cells) ||
                Number(row.dataset.quantity) !== product.units.length ||
                JSON.stringify(JSON.parse(row.dataset.unitIds)) !== JSON.stringify(product.units.map(unit => unit.id));
        })) {
            window.location.reload();
            return;
        }
        document.getElementById('total-count').textContent = data.total;
        document.getElementById('sold-count').textContent = data.sold;
        document.getElementById('available-count').textContent = data.available;
        document.getElementById('showcase-count').textContent = data.showcase_quantity;
        document.getElementById('showcase-products').textContent = data.showcased_products;
        document.getElementById('sales-amount').textContent = `${data.sales_amount} ₽`;
        document.getElementById('sales-unpriced').textContent = data.sales_unpriced ? ` · без цены: ${data.sales_unpriced} шт.` : '';
        data.valuations.forEach((valuation, index) => {
            const row = container.querySelector(`[data-valuation-index="${index}"]`);
            row.querySelectorAll('.valuation-amount').forEach((cell, column) => { cell.textContent = valuation.amounts[column]; });
            row.querySelectorAll('.unpriced-note').forEach((cell, column) => {
                cell.textContent = valuation.unpriced[column] ? `Без цены: ${valuation.unpriced[column]} шт.` : '';
            });
        });
        for (const product of data.products) {
            const row = tableBody.querySelector(`[data-product-id="${product.id}"]`);
            row.dataset.sold = product.sold;
            row.dataset.showcase = product.showcase_quantity;
            row.classList.toggle('sold-out', product.available === 0);
            row.classList.toggle('expiry-expired', product.expiry_status === 'expired');
            row.classList.toggle('expiry-soon', product.expiry_status === 'soon');
            const soldButton = row.querySelector('.sold-badge');
            soldButton.querySelector('.count-text').textContent = `${product.sold} из ${product.units.length}`;
            soldButton.classList.toggle('empty', product.sold === 0);
            soldButton.setAttribute('aria-label', `Продано ${product.sold} из ${product.units.length}`);
            const showcaseButton = row.querySelector('[data-count-kind="showcase"]');
            showcaseButton.classList.toggle('empty', product.showcase_quantity === 0);
            showcaseButton.textContent = product.showcase_quantity > 0 ? `✓ ${product.showcase_quantity} шт.` : '+';
        }
        window.OneAlmaExpiry.refresh(tableBody.querySelectorAll('tr'));
        sortRows();
    }

    tableBody.querySelectorAll('[data-count-kind]').forEach(button => {
        button.addEventListener('click', () => { openCount(button); });
    });
    document.getElementById('count-close').addEventListener('click', closeCount);
    document.addEventListener('keydown', event => { if (event.key === 'Escape') closeCount(); });
    countInput.addEventListener('input', () => { countError.textContent = ''; updateCountControls(); });
    for (const [id, delta] of [['count-minus', -1], ['count-plus', 1]]) {
        document.getElementById(id).addEventListener('click', () => {
            const value = Number(countInput.value);
            countInput.value = Math.max(0, Math.min(Number(countInput.max), (Number.isInteger(value) ? value : 0) + delta));
            countError.textContent = '';
            updateCountControls();
        });
    }
    countForm.addEventListener('submit', async event => {
        event.preventDefault();
        if (!countRow || !countInput.reportValidity()) return;
        const row = countRow;
        setBusy(true);
        countError.textContent = '';
        status.classList.remove('error');
        status.textContent = 'Сохраняю…';
        try {
            const data = await api(`/one_alma/products/${row.dataset.productId}/showcase`, {
                method: 'POST', body: new URLSearchParams({quantity: countInput.value, csrf_token: csrfToken}),
            });
            applyInventory(data);
            status.textContent = 'Сохранено.';
            setBusy(false);
            closeCount();
        } catch (error) {
            countError.textContent = errorMessage(error);
            status.classList.add('error');
            status.textContent = errorMessage(error);
        } finally {
            setBusy(false);
        }
    });

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
        resetImport();
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
    function resetImport() {
        importFingerprint = '';
        importValid = false;
        window.ExcelImportDialog.reset(importDialog);
    }
    importForm.elements.file.addEventListener('change', resetImport);

    function renderImportPreview(preview) {
        const summary = preview.already_imported ? 'Эта поставка уже загружена. Остатки не изменятся.' :
            `Новых позиций: ${preview.added}. Пополнятся: ${preview.updated}. Приход: ${preview.quantity} шт.`;
        const rows = preview.rows.map(item => ({...item,
            details: [item.volume && `Объём: ${item.volume}`, item.expiry && `Годен до: ${item.expiry}`],
            result: preview.already_imported ? 'Уже загружено' : item.action,
        }));
        importValid = window.ExcelImportDialog.render(importDialog, {rows, summary, valid: preview.valid, alreadyImported: preview.already_imported});
        importFingerprint = importValid ? preview.fingerprint : '';
    }

    importForm.addEventListener('submit', async event => {
        event.preventDefault();
        if (busy) return;
        const body = new FormData(importForm);
        body.set('csrf_token', csrfToken);
        if (importFingerprint) body.set('fingerprint', importFingerprint);
        setBusy(true);
        const message = importForm.querySelector('.dialog-status');
        message.textContent = importFingerprint ? 'Сохраняю приход…' : 'Проверяю файл…';
        try {
            const data = await api('/one_alma/import', {method: 'POST', body});
            if (data.preview) renderImportPreview(data.preview);
            else { window.location.reload(); return; }
        } catch (error) {
            message.textContent = errorMessage(error);
        } finally {
            setBusy(false);
            importSubmit.disabled = !importPreview.hidden && !importValid;
        }
    });

    async function deleteProducts(ids) {
        if (!window.confirm('Удалить товар? История оформленных продаж сохранится.')) return;
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

    container.querySelectorAll('.delete-product').forEach(button => {
        button.addEventListener('click', () => { deleteProducts([button.closest('tr').dataset.productId]); });
    });

    function updateSaleControls() {
        if (!saleRow) return;
        const maximum = Number(saleRow.dataset.quantity) - Number(saleRow.dataset.sold);
        const quantity = Number(saleQuantity.value);
        const quantityError = !Number.isInteger(quantity) || quantity < 1 || quantity > maximum ?
            `Укажите целое количество от 1 до ${maximum}.` : '';
        let cents = null, priceError = '';
        try { cents = priceCents(salePrice.value); } catch (error) { priceError = error.message; }
        document.getElementById('sale-quantity-error').textContent = quantityError;
        document.getElementById('sale-price-error').textContent = priceError;
        saleQuantity.setAttribute('aria-invalid', String(Boolean(quantityError)));
        salePrice.setAttribute('aria-invalid', String(Boolean(priceError)));
        document.getElementById('sale-minus').disabled = busy || quantity <= 1;
        document.getElementById('sale-plus').disabled = busy || quantity >= maximum;
        document.getElementById('sale-save').disabled = busy || Boolean(quantityError || priceError);
        document.getElementById('sale-total').textContent = quantityError || priceError ? '—' :
            rubles(cents === null ? null : cents * quantity);
        return !quantityError && !priceError;
    }

    function openSale(row) {
        saleRow = row;
        saleRequestId = crypto.randomUUID();
        saleForm.reset();
        const cells = JSON.parse(row.dataset.cells);
        const available = Number(row.dataset.quantity) - Number(row.dataset.sold);
        document.getElementById('sale-context').textContent = cells[2];
        document.getElementById('sale-article').value = cells[1];
        document.getElementById('sale-date').value = moscowTime(new Date());
        document.getElementById('sale-price-note').textContent = `Цена ЦБ: ${rubles(priceCents(cells[5]))}. Изменение сохранится только в этой продаже.`;
        salePrice.value = priceCents(cells[5]) === null ? '' : cells[5];
        saleQuantity.value = '1';
        saleQuantity.max = available;
        document.getElementById('sale-stock').textContent = `Можно продать до ${available} шт.`;
        document.getElementById('sale-error').textContent = '';
        updateSaleControls();
        saleDialog.showModal();
        document.getElementById('sale-customer').focus();
    }

    async function loadHistory() {
        const row = historyRow;
        if (!row) return;
        const content = document.getElementById('history-content');
        const summary = document.getElementById('history-summary');
        try {
            const data = await api(`/one_alma/products/${row.dataset.productId}/history`, {method: 'GET'});
            if (row !== historyRow || !historyDialog.open) return;
            summary.textContent = `Продано: ${data.sold} шт. · Сумма: ${data.amount} ₽` +
                (data.unpriced ? ` · без цены: ${data.unpriced} шт.` : '') +
                (data.legacy_sold ? ` · Ранее отмечено без записи в истории: ${data.legacy_sold} шт.` : '');
            content.replaceChildren();
            if (!data.entries.length) {
                const empty = document.createElement('p');
                empty.className = 'empty-message'; empty.textContent = 'Изменений пока нет.';
                content.appendChild(empty);
                return;
            }
            const scroll = document.createElement('div'); scroll.className = 'inventory-scroll';
            const table = document.createElement('table'); table.className = 'history-table';
            const head = table.createTHead().insertRow();
            for (const label of ['Дата · Москва', 'Товар', 'Действие', 'Кому', 'Кол-во, шт.', 'Цена за шт., ₽', 'Сумма, ₽', '']) {
                const cell = document.createElement('th'); cell.textContent = label; head.appendChild(cell);
            }
            const body = table.createTBody();
            for (const entry of data.entries) {
                const line = body.insertRow(); line.classList.toggle('cancelled', entry.cancelled);
                entry.values.forEach(value => { line.insertCell().textContent = value; });
                const action = line.insertCell();
                if (entry.can_cancel) {
                    const button = document.createElement('button'); button.type = 'button';
                    button.className = 'secondary-button'; button.textContent = 'Отменить';
                    button.disabled = busy;
                    button.addEventListener('click', () => {
                        cancelSaleId = entry.sale_id;
                        document.getElementById('undo-text').textContent = `${entry.values[2]}. ${entry.values[3]}, ${entry.values[4].replace('−', '')} шт. Вернуть их в остаток?`;
                        document.getElementById('undo-error').textContent = '';
                        undoDialog.showModal();
                    });
                    action.appendChild(button);
                }
            }
            scroll.appendChild(table); content.appendChild(scroll);
        } catch (error) {
            if (row !== historyRow || !historyDialog.open) return;
            summary.textContent = '';
            content.textContent = errorMessage(error);
        }
    }

    function openHistory(row) {
        historyRow = row;
        const cells = JSON.parse(row.dataset.cells);
        document.getElementById('history-context').textContent = `${cells[1]} · ${cells[2]}`;
        document.getElementById('history-summary').textContent = '';
        document.getElementById('history-content').textContent = 'Загружаю…';
        historyDialog.showModal();
        loadHistory();
    }

    tableBody.querySelectorAll('.record-sale').forEach(button => {
        button.addEventListener('click', () => openSale(button.closest('tr')));
    });
    tableBody.querySelectorAll('.product-history').forEach(button => {
        button.addEventListener('click', () => openHistory(button.closest('tr')));
    });
    [salePrice, saleQuantity].forEach(input => input.addEventListener('input', updateSaleControls));
    for (const [id, delta] of [['sale-minus', -1], ['sale-plus', 1]]) {
        document.getElementById(id).addEventListener('click', () => {
            saleQuantity.value = Math.max(1, Math.min(Number(saleQuantity.max), (Number(saleQuantity.value) || 1) + delta));
            updateSaleControls();
        });
    }
    saleForm.addEventListener('submit', async event => {
        event.preventDefault();
        if (busy || !saleRow || !updateSaleControls()) return;
        const body = new URLSearchParams({quantity: saleQuantity.value,
            customer: document.getElementById('sale-customer').value, unit_price: salePrice.value,
            request_id: saleRequestId, csrf_token: csrfToken});
        setBusy(true);
        document.getElementById('sale-error').textContent = '';
        try {
            const data = await api(`/one_alma/products/${saleRow.dataset.productId}/sales`, {method: 'POST', body});
            applyInventory(data);
            saleDialog.close();
            status.classList.remove('error'); status.textContent = 'Продажа оформлена.';
        } catch (error) {
            document.getElementById('sale-error').textContent = errorMessage(error);
        } finally { setBusy(false); }
    });
    document.getElementById('sale-history').addEventListener('click', () => {
        saleDialog.close(); openHistory(saleRow);
    });
    document.getElementById('undo-confirm').addEventListener('click', async () => {
        if (busy || cancelSaleId === null) return;
        setBusy(true);
        try {
            const data = await api(`/one_alma/sales/${cancelSaleId}/cancel`, {
                method: 'POST', body: new URLSearchParams({csrf_token: csrfToken}),
            });
            applyInventory(data);
            undoDialog.close();
            await loadHistory();
            status.classList.remove('error'); status.textContent = 'Продажа отменена.';
        } catch (error) { document.getElementById('undo-error').textContent = errorMessage(error); }
        finally { setBusy(false); }
    });
    container.querySelectorAll('[data-close]').forEach(button => {
        button.addEventListener('click', () => { if (!busy) button.closest('dialog').close(); });
    });
    container.querySelectorAll('dialog').forEach(dialog => {
        dialog.addEventListener('cancel', event => { if (busy) event.preventDefault(); });
    });
    setInterval(() => {
        if (saleDialog.open) document.getElementById('sale-date').value = moscowTime(new Date());
    }, 1000);
    sortRows();
    setInterval(() => { refreshSession().catch(() => {}); }, 10 * 60 * 1000);
})();
