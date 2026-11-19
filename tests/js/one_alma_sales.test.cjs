const assert = require('node:assert/strict');
const {test} = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

class Element {
    constructor(tag = 'div') {
        this.tagName = tag;
        this.children = [];
        this.listeners = new Map();
        this.dataset = {csrfToken: 'test-csrf'};
        this.attributes = {};
        this.value = '';
        this.rows = [];
        this.classList = {add() {}, remove() {}};
    }
    set textContent(value) { this.text = value; this.children = []; }
    get textContent() { return [this.text || '', ...this.children.map(child => child.textContent)].join(' '); }
    append(...children) { this.children.push(...children); }
    appendChild(child) { this.append(child); return child; }
    replaceChildren() { this.text = ''; this.children = []; }
    querySelectorAll() { return []; }
    querySelector() { return new Element(); }
    setAttribute(name, value) { this.attributes[name] = value; }
    addEventListener(name, callback) { this.listeners.set(name, callback); }
    async click() { await this.listeners.get('click')?.({preventDefault() {}}); }
    showModal() { this.open = true; }
    close() { this.open = false; }
}

function sale(id, overrides = {}) {
    return {id, customer: 'Анна & <компания>', cells: ['1', '0262', 'Крем', '30 мл'], quantity: 2,
        price: '80,25', amount: '160,50', created_at: '19.11.2026 11:35:00', cancelled_at: null,
        can_cancel: true, ...overrides};
}

function page(responses) {
    const elements = new Map();
    const calls = [];
    const get = id => {
        if (id === 'show-cancelled-sales') return null;
        if (!elements.has(id)) elements.set(id, new Element());
        return elements.get(id);
    };
    const container = new Element();
    container.querySelector = selector => get(selector);
    get('import-form').elements = {file: new Element('input')};
    const source = fs.readFileSync(path.join(__dirname, '../../templates/one_alma.js'), 'utf8');
    vm.runInNewContext(source, {
        document: {querySelector: () => container, getElementById: get, createElement: tag => new Element(tag), addEventListener() {}},
        window: {location: {search: ''}, OneAlmaSearch: {TableSearch: class {apply() {}}}, OneAlmaExpiry: {refresh() {}}},
        URLSearchParams, Intl, Date, setInterval() {},
        fetch: async (url, options) => {
            calls.push({url, options});
            assert.ok(responses.length, `Unexpected request: ${url}`);
            return Response.json(responses.shift());
        },
    });
    return {get, calls};
}

test('sales modal shows only active receipts without a cancelled-sales checkbox', async () => {
    const ui = page([{sold: 2, amount: '160,50', unpriced: 0,
        sales: [sale(2), sale(1, {customer: 'Отменённый покупатель', cancelled_at: '19.11.2026 12:00:00'})]}]);

    await ui.get('sales-history').click();
    await new Promise(setImmediate);

    assert.equal(ui.get('sales-history-dialog').open, true);
    assert.equal(ui.get('sales-history-content').children.length, 1);
    assert.match(ui.get('sales-history-content').textContent, /Продажа #2/);
    assert.match(ui.get('sales-history-content').textContent, /Анна & <компания>/);
    assert.doesNotMatch(ui.get('sales-history-content').textContent, /Отменённый|Отменена:|Продажа #1/);
    assert.match(ui.get('sales-history-summary').textContent, /Продано: 2 шт.*Сумма: 160,50/);
    assert.equal(ui.calls[0].url, '/one_alma/sales');
    assert.equal(ui.calls[0].options.credentials, 'same-origin');
});

test('cancelling a sale reloads receipts and totals and removes the cancelled receipt immediately', async () => {
    const ui = page([
        {sold: 2, amount: '160,50', unpriced: 0, sales: [sale(2)]},
        {products: [], valuations: [], sold: 0, total: 2, available: 2, written_off: 0, sales_amount: '0,00', sales_unpriced: 0},
        {sold: 0, amount: '0,00', unpriced: 0, sales: []},
    ]);
    await ui.get('sales-history').click();
    await new Promise(setImmediate);
    const receipt = ui.get('sales-history-content').children[0];
    const cancel = receipt.children.at(-1).children.find(child => child.tagName === 'button');

    await cancel.click();
    await ui.get('undo-confirm').click();

    assert.equal(ui.get('undo-dialog').open, false);
    assert.equal(ui.get('sales-history-dialog').open, true);
    assert.equal(ui.get('sales-history-content').textContent.trim(), 'Продаж пока нет.');
    assert.match(ui.get('sales-history-summary').textContent, /Продано: 0 шт.*Сумма: 0,00/);
    assert.deepEqual(ui.calls.map(call => call.url), ['/one_alma/sales', '/one_alma/sales/2/cancel', '/one_alma/sales']);
    assert.equal(ui.calls[1].options.body.get('csrf_token'), 'test-csrf');
});

test('receipt without a price keeps its date and PDF link and has no cancel action for a deleted product', async () => {
    const ui = page([{sold: 1, amount: '0,00', unpriced: 1,
        sales: [sale(7, {quantity: 1, price: '—', amount: '—', can_cancel: false})]}]);

    await ui.get('sales-history').click();
    await new Promise(setImmediate);

    const receipt = ui.get('sales-history-content').children[0];
    const actions = receipt.children.at(-1);
    assert.match(receipt.textContent, /19.11.2026 11:35:00/);
    assert.match(receipt.textContent, /1 шт. × — ₽/);
    assert.match(ui.get('sales-history-summary').textContent, /Без цены: 1 шт./);
    assert.equal(actions.children.length, 1);
    assert.equal(actions.children[0].href, '/one_alma/sales/pdf?sale_id=7');
});
