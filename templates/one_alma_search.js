((root) => {
    'use strict';

    function normalize(value) {
        return String(value ?? '').normalize('NFKC').toLocaleLowerCase('ru-RU')
            .replace(/ё/g, 'е').replace(/,/g, '.').replace(/\s+/g, ' ').trim();
    }

    function matchesRow(row, query) {
        const words = normalize(query).split(' ').filter(Boolean);
        if (!words.length) return true;
        const cells = JSON.parse(row.dataset.cells);
        const prices = cells.slice(5, 8).map(value => normalize(value).replace(/\s/g, ''));
        const text = normalize([...cells, ...prices,
            `Витрина ${row.dataset.showcase} шт.`,
            `Продано ${row.dataset.sold} из ${row.dataset.quantity}`,
            `Списан ${row.dataset.writtenOff || 0} шт.`].join(' '));
        return words.every(word => text.includes(word));
    }

    class TableSearch {
        constructor({body, toggle, field, input, clear, empty, active, events}) {
            Object.assign(this, {body, toggle, field, input, clear, empty, active});
            active.addEventListener('change', () => this.apply());
            events?.addEventListener('onealma:expiry-updated', () => this.apply());
            toggle.addEventListener('click', () => {
                if (field.hidden) {
                    field.hidden = false;
                    toggle.setAttribute('aria-expanded', 'true');
                    input.focus();
                } else this.close();
            });
            input.addEventListener('input', () => this.apply());
            input.addEventListener('keydown', event => {
                if (event.key !== 'Escape') return;
                event.preventDefault();
                this.close();
                toggle.focus();
            });
            clear.addEventListener('click', () => {
                input.value = '';
                this.apply();
                input.focus();
            });
        }

        close() {
            this.field.hidden = true;
            this.toggle.setAttribute('aria-expanded', 'false');
            this.input.value = '';
            this.apply();
        }

        apply() {
            let matched = 0;
            for (const row of this.body.querySelectorAll('[data-product-id]')) {
                row.hidden = (this.active.checked && !isActive(row)) || !matchesRow(row, this.input.value);
                if (!row.hidden) matched++;
            }
            this.clear.hidden = !this.input.value;
            this.empty.hidden = matched > 0;
            return matched;
        }
    }

    function isActive(row) {
        const remaining = Number(row.dataset.quantity) - Number(row.dataset.sold) - Number(row.dataset.writtenOff || 0);
        return remaining > 0 && !row.classList.contains('expiry-expired');
    }

    const api = {matchesRow, isActive, TableSearch};
    if (typeof module !== 'undefined' && module.exports) module.exports = api;
    else root.OneAlmaSearch = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
