"use strict";

class InventoryPage {
    constructor(root) {
        this.root = root;
        this.csrf = root.dataset.csrfToken;
        this.items = new Map();
        this.editing = null;
        this.pendingConfirmation = null;
        this.importData = null;
        this.importBusy = false;
        this.sortField = "id";
        this.descending = false;
        this.refreshVersion = 0;
        this.busyRows = new Set();
        this.fields = ["article", "brand", "name", "purchase_price", "sale_price", "expiry", "quantity"];
        this.columns = ["№", "Артикул", "Бренд", "Название", "Закупочная стоимость", "Цена продажи", "Срок годности", "Количество"];
        this.bind();
        this.refresh().catch(error => this.status(error.message, true));
        this.watchExpiryDay();
    }

    element(tag, text, className) {
        const node = document.createElement(tag);
        if (text !== undefined) node.textContent = text;
        if (className) node.className = className;
        return node;
    }

    bind() {
        document.querySelectorAll("[data-sort]").forEach(button => button.addEventListener("click", () => {
            this.descending = this.sortField === button.dataset.sort ? !this.descending : false;
            this.sortField = button.dataset.sort;
            document.querySelectorAll("[data-sort]").forEach(header => {
                const active = header.dataset.sort === this.sortField;
                header.closest("th").setAttribute("aria-sort", active ? this.descending ? "descending" : "ascending" : "none");
                header.querySelector(".sort-arrow").textContent = active ? this.descending ? "↓" : "↑" : "↕";
            });
            document.getElementById("download-pdf").href = `/inventory/pdf?sort=${this.sortField}&descending=${this.descending}`;
            this.refresh().catch(error => this.status(error.message, true));
        }));
        document.querySelectorAll("[data-open]").forEach(button => button.addEventListener("click", () => this.open(button.dataset.open)));
        document.querySelectorAll("[data-close]").forEach(button => button.addEventListener("click", () => button.closest("dialog").close()));
        document.querySelectorAll("dialog").forEach(dialog => dialog.addEventListener("click", event => {
            const rect = dialog.getBoundingClientRect();
            if (dialog.dataset.busy !== 'true' && event.target === dialog && (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom)) dialog.close();
        }));
        document.getElementById('import-dialog').addEventListener('cancel', event => {
            if (this.importBusy) event.preventDefault();
        });
        document.getElementById("add-product").addEventListener("click", () => this.productEditor());
        document.getElementById("product-form").addEventListener("submit", event => this.saveProduct(event));
        document.getElementById("import-form").addEventListener("submit", event => this.importExcel(event));
        document.getElementById("import-form").addEventListener("change", () => this.resetImport());
        document.getElementById("show-history").addEventListener("click", () => {
            this.open("history-dialog");
            this.loadHistory().catch(error => this.error("history-dialog", error.message));
        });
        document.getElementById("save-snapshot").addEventListener("click", () => {
            this.confirm("Сохранить инвентаризацию?", async () => {
                const result = await this.request("/inventory/snapshots", "POST");
                this.status(result.detail);
            });
        });
        document.getElementById("confirm-yes").addEventListener("click", async event => {
            const button = event.currentTarget;
            button.disabled = true;
            try {
                await this.pendingConfirmation();
                document.getElementById("confirm-dialog").close();
            } catch (error) { this.error("confirm-dialog", error.message); }
            finally { button.disabled = false; }
        });
    }

    open(id) {
        if (id === 'import-dialog') {
            document.getElementById('import-form').reset();
            this.resetImport();
        }
        this.error(id, "");
        document.getElementById(id).showModal();
    }

    error(id, message) { document.querySelector(`#${id} .form-error`).textContent = message; }

    status(message, failed = false) {
        const status = document.getElementById("page-status");
        status.textContent = message;
        status.classList.toggle("error", failed);
    }

    async request(url, method = "GET", body = null) {
        const headers = {"X-CSRF-Token": this.csrf};
        if (body && !(body instanceof FormData)) {
            headers["Content-Type"] = "application/json";
            body = JSON.stringify(body);
        }
        const response = await fetch(url, {method, headers, body, credentials: "same-origin", cache: "no-store"});
        const result = await response.json().catch(() => ({}));
        if (!response.ok) {
            const detail = typeof result.detail === "string" ? result.detail : "Проверьте поля: артикул до 64 цифр, тексты до 255 символов, целое количество и срок ММ.ГГГГ.";
            throw new Error(response.status === 401 ? "Сессия завершена. Войдите снова и обновите страницу." : detail);
        }
        return result;
    }

    async refresh() {
        const version = ++this.refreshVersion;
        const result = await this.request(`/inventory/items?sort=${this.sortField}&descending=${this.descending}`);
        if (version !== this.refreshVersion) return;
        this.items = new Map(result.items.map(item => [item.id, item]));
        const body = document.getElementById("products-body");
        body.replaceChildren();
        if (!result.items.length) {
            const row = this.element("tr");
            const cell = this.element("td", undefined, "empty-state");
            cell.colSpan = 9;
            const icon = this.element("img");
            icon.src = "/static/images/inventory.svg";
            icon.width = icon.height = 54;
            icon.alt = "";
            cell.append(icon, this.element("div", "Товаров пока нет"));
            row.append(cell);
            body.append(row);
        } else result.items.forEach(item => body.append(this.productRow(item)));
    }

    watchExpiryDay() {
        const calendar = new Intl.DateTimeFormat("en-CA", {timeZone: "Europe/Moscow", year: "numeric", month: "2-digit", day: "2-digit"});
        let lastDay = calendar.format(new Date());
        const update = async () => {
            if (document.hidden) return;
            const day = calendar.format(new Date());
            if (day === lastDay) return;
            lastDay = day;
            try { await this.refresh(); }
            catch (error) {
                lastDay = "";
                this.status(error.message, true);
            }
        };
        setInterval(update, 60000);
        document.addEventListener("visibilitychange", update);
        window.addEventListener("focus", update);
    }

    productRow(item, historical = false) {
        const row = this.element("tr", undefined, `expiry-${item.expiry_status}`);
        [item.id, item.article, item.brand, item.name, item.purchase_price, item.sale_price, item.expiry].forEach(value => row.append(this.element("td", String(value || "—"))));
        row.children[6].title = item.expiry_title || "Срок не указан";
        const quantity = this.element("td");
        if (historical) quantity.textContent = item.quantity;
        else {
            const stepper = this.element("div", undefined, "quantity-stepper");
            const minus = this.element("button", "−");
            minus.type = "button";
            minus.setAttribute("aria-label", `Уменьшить количество: ${item.name}`);
            minus.disabled = item.quantity === "0" || this.busyRows.has(item.id);
            minus.addEventListener("click", () => this.step(item.id, -1));
            const count = this.element("span", item.quantity, "quantity-value");
            const plus = this.element("button", "+");
            plus.type = "button";
            plus.disabled = this.busyRows.has(item.id);
            plus.setAttribute("aria-label", `Увеличить количество: ${item.name}`);
            plus.addEventListener("click", () => this.step(item.id, 1));
            stepper.append(minus, count, plus);
            quantity.append(stepper);
        }
        row.append(quantity);
        if (!historical) {
            const cell = this.element("td");
            const actions = this.element("div", undefined, "row-actions");
            actions.append(this.iconButton("edit", `Изменить товар: ${item.name}`, () => this.productEditor(item.id)));
            actions.append(this.iconButton("delete", `Удалить товар: ${item.name}`, () => this.confirm("Удалить товар?", async () => {
                const result = await this.request(`/inventory/products/${item.id}`, "DELETE");
                await this.refresh();
                this.status(result.detail);
            })));
            cell.append(actions);
            row.append(cell);
        }
        return row;
    }

    iconButton(kind, label, action) {
        const button = this.element("button", undefined, "icon-button");
        button.type = "button";
        button.title = label;
        button.setAttribute("aria-label", label);
        // Static, trusted SVG only. All product and import text uses textContent.
        button.innerHTML = kind === "edit" ? '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m16 3 5 5-12 12-6 1 1-6L16 3Zm-3 3 5 5"/></svg>' : '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h16M9 6V3h6v3M6 6l1 15h10l1-15M10 10v7m4-7v7"/></svg>';
        button.addEventListener("click", action);
        return button;
    }

    productEditor(id = null) {
        this.editing = id;
        const form = document.getElementById("product-form");
        form.reset();
        if (id !== null) this.fields.forEach(field => { form.elements[field].value = this.items.get(id)[field]; });
        document.getElementById("product-title").textContent = id === null ? "Добавить товар" : "Изменить товар";
        this.open("product-dialog");
    }

    async submit(event, dialogId, action) {
        event.preventDefault();
        const button = event.currentTarget.querySelector('button[type="submit"]');
        button.disabled = true;
        this.error(dialogId, "");
        try {
            const result = await action();
            document.getElementById(dialogId).close();
            await this.refresh();
            this.status(result.detail);
        } catch (error) {
            if (document.getElementById(dialogId).open) this.error(dialogId, error.message);
            else this.status(error.message, true);
        } finally { button.disabled = false; }
    }

    saveProduct(event) {
        const data = Object.fromEntries(new FormData(event.currentTarget));
        const id = this.editing;
        return this.submit(event, "product-dialog", () => this.request(id === null ? "/inventory/products" : `/inventory/products/${id}`, id === null ? "POST" : "PUT", data));
    }

    async step(id, delta) {
        if (this.busyRows.has(id)) return;
        this.busyRows.add(id);
        document.querySelectorAll("#products-body button").forEach(button => { button.disabled = true; });
        try {
            await this.request(`/inventory/products/${id}/quantity`, "POST", {delta});
            this.status("Количество сохранено");
        } catch (error) { this.status(error.message, true); }
        finally {
            this.busyRows.delete(id);
            this.refresh().catch(error => this.status(error.message, true));
        }
    }

    resetImport() {
        this.importData = null;
        window.ExcelImportDialog.reset(document.getElementById('import-dialog'));
    }

    async importExcel(event) {
        event.preventDefault();
        if (this.importBusy) return;
        if (this.importData) {
            const data = this.importData;
            this.importBusy = true;
            window.ExcelImportDialog.setBusy(document.getElementById('import-dialog'), true);
            try {
                return await this.submit(event, 'import-dialog', async () => {
                    try {
                        const result = await this.request('/inventory/import', 'POST', data);
                        this.resetImport();
                        return result;
                    } catch (error) {
                        this.resetImport();
                        throw error;
                    }
                });
            } finally {
                this.importBusy = false;
                window.ExcelImportDialog.setBusy(document.getElementById('import-dialog'), false);
            }
        }
        const button = document.getElementById('import-submit');
        const data = new FormData(event.currentTarget);
        this.importBusy = true;
        window.ExcelImportDialog.setBusy(document.getElementById('import-dialog'), true);
        this.error('import-dialog', '');
        let canImport = false;
        try {
            const result = await this.request('/inventory/import', 'POST', data);
            canImport = this.renderImportPreview(result.preview);
            if (canImport) {
                data.set('fingerprint', result.preview.fingerprint);
                this.importData = data;
            }
        } catch (error) { this.error('import-dialog', error.message); }
        finally {
            this.importBusy = false;
            window.ExcelImportDialog.setBusy(document.getElementById('import-dialog'), false);
            button.disabled = !document.getElementById('import-preview').hidden && !canImport;
        }
    }

    renderImportPreview(preview) {
        const rows = preview.rows.map(item => {
            const changes = this.fields.filter(field => field !== 'quantity' && item.before && item.before[field] !== item.after[field]).map(field => {
                const title = this.columns[this.fields.indexOf(field) + 1];
                return `${title}: ${item.before[field] || '—'} → ${item.after[field] || '—'}`;
            });
            return {
                row: item.row, error: item.error, article: item.after.article, name: item.after.name,
                details: [item.after.brand && `Бренд: ${item.after.brand}`, item.after.expiry && `Годен до: ${item.after.expiry}`],
                quantity: item.after.quantity, before: item.before?.quantity ?? 0, after: item.after.quantity,
                result: [item.action === 'add' ? 'Новый товар' : 'Обновление', ...changes].join('\n'),
            };
        });
        return window.ExcelImportDialog.render(document.getElementById('import-dialog'), {
            rows, valid: preview.valid,
            summary: `Новых позиций: ${preview.added}. Обновятся: ${preview.updated}.`,
        });
    }

    confirm(title, action) {
        this.pendingConfirmation = action;
        document.getElementById("confirm-title").textContent = title;
        this.open("confirm-dialog");
    }

    async loadHistory() {
        const container = document.getElementById("history-content");
        container.replaceChildren(this.element("p", "Загрузка…", "history-empty"));
        const result = await this.request("/inventory/history");
        container.replaceChildren();
        if (!result.snapshots.length) container.append(this.element("p", "Инвентаризаций пока нет", "history-empty"));
        result.snapshots.forEach(snapshot => {
            const entry = this.element("div", undefined, "history-entry");
            const details = this.element("details");
            const summary = this.element("summary");
            summary.append(this.element("strong", `#${snapshot.id}`), document.createTextNode(`${snapshot.created_at} — ${snapshot.ended_at || "по настоящее время"}`));
            details.append(summary);
            const scroll = this.element("div", undefined, "table-scroll");
            scroll.tabIndex = 0;
            const table = this.element("table", undefined, "stock-table history-table");
            const header = this.element("thead");
            const headerRow = this.element("tr");
            this.columns.forEach(name => headerRow.append(this.element("th", name)));
            header.append(headerRow);
            const body = this.element("tbody");
            snapshot.items.forEach(item => body.append(this.productRow(item, true)));
            if (!snapshot.items.length) {
                const row = this.element("tr");
                const cell = this.element("td", "Товаров пока нет", "history-empty");
                cell.colSpan = 8;
                row.append(cell);
                body.append(row);
            }
            table.append(header, body);
            scroll.append(table);
            details.append(scroll);
            const remove = this.element("button", "Отменить", "secondary-button history-delete");
            remove.type = "button";
            remove.setAttribute("aria-label", `Отменить инвентаризацию #${snapshot.id}`);
            remove.addEventListener("click", () => this.confirm("Удалить инвентаризацию?", async () => {
                const result = await this.request(`/inventory/history/${snapshot.id}`, "DELETE");
                await this.loadHistory();
                this.status(result.detail);
            }));
            entry.append(details, remove);
            container.append(entry);
        });
    }
}

if (typeof module !== "undefined" && module.exports) module.exports = {InventoryPage};
else new InventoryPage(document.querySelector(".clinic-inventory"));
