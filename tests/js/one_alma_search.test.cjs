const assert = require('node:assert/strict');
const {test} = require('node:test');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const {matchesRow, isActive, TableSearch} = require('../../templates/one_alma_search.js');

function row(cells, counts = {}) {
    const classes = new Set();
    return {dataset: {cells: JSON.stringify(cells), quantity: '7', sold: '3', showcase: '2', writtenOff: '1', ...counts},
        hidden: false, classList: {contains: name => classes.has(name), add: name => classes.add(name), remove: name => classes.delete(name)}};
}

function cream() {
    return row(['45', '0262', 'Зелёный крем для лица', '30 мл', '05.2028', '1 441,94', '3 239,00', '5 400,00']);
}

class Control extends EventTarget {
    constructor() { super(); this.hidden = false; this.value = ''; this.attributes = {}; }
    setAttribute(name, value) { this.attributes[name] = value; }
    focus() { this.focused = true; }
}

function controls(rows) {
    const elements = Object.fromEntries(['toggle', 'field', 'input', 'clear', 'empty', 'active', 'events'].map(name => [name, new Control()]));
    elements.active.checked = true;
    elements.field.hidden = true;
    elements.toggle.setAttribute('aria-expanded', 'false');
    const body = {querySelectorAll: () => rows};
    return {...elements, search: new TableSearch({body, ...elements})};
}

for (const query of ['0262', 'ЗЕЛЕНЫЙ', 'зелёный крем', 'крем 30', '05.2028', '1441,94', '1 441.94', '3239', '45', 'списан', '']) {
    test(`search matches the visible table values for ${JSON.stringify(query)}`, () => {
        const product = cream();
        const before = structuredClone(product.dataset);

        const matches = matchesRow(product, query);

        assert.equal(matches, true);
        assert.deepEqual(product.dataset, before);
    });
}

for (const query of ['нет такого товара', 'крем 500 мл', '<script>alert(1)</script>', '123456789']) {
    test(`search excludes a row for ${JSON.stringify(query)}`, () => {
        const product = cream();

        const matches = matchesRow(product, query);

        assert.equal(matches, false);
    });
}

test('magnifier opens the input and focuses it', () => {
    const product = cream();
    const ui = controls([product]);

    ui.toggle.dispatchEvent(new Event('click'));

    assert.equal(ui.field.hidden, false);
    assert.equal(ui.toggle.attributes['aria-expanded'], 'true');
    assert.equal(ui.input.focused, true);
});

test('clicking an open magnifier clears and hides the input', () => {
    const product = cream(), ui = controls([product]);
    ui.toggle.dispatchEvent(new Event('click'));
    ui.input.value = 'нет совпадений';
    ui.input.dispatchEvent(new Event('input'));

    ui.toggle.dispatchEvent(new Event('click'));

    assert.equal(ui.field.hidden, true);
    assert.equal(ui.toggle.attributes['aria-expanded'], 'false');
    assert.equal(ui.input.value, '');
    assert.equal(product.hidden, false);
});

test('typing searches all rows including the last row and does not remove them', () => {
    const rows = Array.from({length: 120}, cream);
    rows.push(row(['200', '8450', 'Маска после процедур', '15 мл', '08.2027', '283,17', '670', '1190']));
    const originalData = rows.map(product => structuredClone(product.dataset));
    const ui = controls(rows);
    ui.input.value = 'маска процедур';

    ui.input.dispatchEvent(new Event('input'));

    assert.equal(rows.filter(product => !product.hidden).length, 1);
    assert.equal(rows.at(-1).hidden, false);
    assert.equal(ui.empty.hidden, true);
    assert.deepEqual(rows.map(product => product.dataset), originalData);
});

test('clearing a failed search restores every row and hides the empty message', () => {
    const rows = [cream(), cream()];
    const ui = controls(rows);
    ui.input.value = 'нет совпадений';
    ui.search.apply();
    const emptyBeforeClearing = !ui.empty.hidden;

    ui.clear.dispatchEvent(new Event('click'));

    assert.ok(rows.every(product => !product.hidden));
    assert.equal(emptyBeforeClearing, true);
    assert.equal(ui.input.value, '');
    assert.equal(ui.clear.hidden, true);
    assert.equal(ui.empty.hidden, true);
    assert.equal(ui.input.focused, true);
});

test('Escape closes the input and restores all rows', () => {
    const product = cream(), ui = controls([product]);
    ui.toggle.dispatchEvent(new Event('click'));
    ui.input.value = 'нет совпадений';
    ui.search.apply();
    const event = new Event('keydown', {cancelable: true});
    Object.defineProperty(event, 'key', {value: 'Escape'});

    ui.input.dispatchEvent(event);

    assert.equal(event.defaultPrevented, true);
    assert.equal(ui.field.hidden, true);
    assert.equal(ui.input.value, '');
    assert.equal(product.hidden, false);
    assert.equal(ui.toggle.focused, true);
});

test('filter uses updated cells after an edit while retaining the entered query', () => {
    const product = cream(), ui = controls([product]);
    ui.input.value = 'крем';
    ui.search.apply();
    product.dataset.cells = JSON.stringify(['45', '0262', 'Маска', '30 мл', '05.2028', '', '', '']);

    ui.search.apply();

    assert.equal(ui.input.value, 'крем');
    assert.equal(product.hidden, true);
    assert.equal(ui.empty.hidden, false);
});

test('empty catalogue shows the empty state without fake product rows', () => {
    const ui = controls([]);

    const count = ui.search.apply();

    assert.equal(count, 0);
    assert.equal(ui.empty.hidden, false);
});

for (const [sold, writtenOff, expired, expected] of [
    [0, 1, false, true], [3, 1, false, true], [4, 1, false, false],
    [5, 0, false, false], [0, 5, false, false], [0, 0, true, false], [0, 1, true, false],
]) {
    test(`active criterion for five units, sold ${sold}, written ${writtenOff}, expired ${expired}`, () => {
        const product = row(['1', '0262', 'Крем', '30 мл', '05.2028', '', '', ''],
            {quantity: '5', sold: String(sold), writtenOff: String(writtenOff)});
        if (expired) product.classList.add('expiry-expired');

        const result = isActive(product);

        assert.equal(result, expected);
    });
}

test('unchecking active combines with search and reveals expired and zero-stock rows', () => {
    const partial = cream(), sold = cream(), written = cream(), expired = cream();
    sold.dataset.sold = '7'; sold.dataset.writtenOff = '0';
    written.dataset.sold = '0'; written.dataset.writtenOff = '7';
    expired.classList.add('expiry-expired');
    const rows = [partial, sold, written, expired], original = rows.map(product => structuredClone(product.dataset));
    const ui = controls(rows);
    ui.input.value = 'крем';
    ui.search.apply();
    const activeRows = rows.filter(product => !product.hidden);

    ui.active.checked = false;
    ui.active.dispatchEvent(new Event('change'));

    assert.deepEqual(activeRows, [partial]);
    assert.ok(rows.every(product => !product.hidden));
    assert.deepEqual(rows.map(product => product.dataset), original);
});

test('yellow expiry stays active and midnight expiry event reapplies the filter', () => {
    const product = cream(), ui = controls([product]);
    product.classList.add('expiry-soon');
    ui.search.apply();
    const beforeMidnight = product.hidden;
    product.classList.remove('expiry-soon');
    product.classList.add('expiry-expired');

    ui.events.dispatchEvent(new Event('onealma:expiry-updated'));

    assert.equal(beforeMidnight, false);
    assert.equal(product.hidden, true);
    assert.equal(ui.empty.hidden, false);
});

test('cancelling a full writeoff brings a non-expired product back into active results', () => {
    const product = cream(), ui = controls([product]);
    product.dataset.sold = '0'; product.dataset.writtenOff = '7';
    ui.search.apply();
    const beforeCancellation = product.hidden;
    product.dataset.writtenOff = '1';

    ui.search.apply();

    assert.equal(beforeCancellation, true);
    assert.equal(product.hidden, false);
});

test('Moscow midnight broadcasts refreshed expiry once to the product filter', () => {
    let now = '2026-11-30T20:59:00Z', tick;
    const document = new Control();
    document.readyState = 'complete';
    document.querySelectorAll = () => [];
    let updates = 0;
    document.addEventListener('onealma:expiry-updated', () => updates++);
    const context = {document, window: new Control(), Event, Intl,
        Date: class extends Date { constructor(...args) { super(...(args.length ? args : [now])); } },
        setInterval(callback) { tick = callback; }};
    const source = fs.readFileSync(path.join(__dirname, '../../templates/one_alma_expiry.js'), 'utf8');
    vm.runInNewContext(source, context);
    const beforeMidnight = updates;
    now = '2026-11-30T21:00:00Z';

    tick();
    tick();

    assert.equal(beforeMidnight, 1);
    assert.equal(updates, 2);
});
