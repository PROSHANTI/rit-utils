const assert = require('node:assert/strict');
const {test} = require('node:test');
const {InventoryPage, matchesInventoryItem} = require('../../templates/inventory.js');

function product(overrides = {}) {
    return {id: 104729, article: '000062', brand: 'EMANSI', name: 'Зелёный крем с алоэ',
        purchase_price: '1 234,56', sale_price: '2 345,67', expiry: '08.2029', quantity: '19',
        expiry_status: 'normal', ...overrides};
}

for (const [field, query] of [
    ['id', '104729'], ['article', '000062'], ['brand', 'emansi'], ['name', 'алоэ'],
    ['purchase_price', '1234,56'], ['sale_price', '2 345.67'], ['expiry', '08.2029'], ['quantity', '19'],
]) {
    test(`inventory search includes the ${field} column without changing product data`, () => {
        const item = product(), before = structuredClone(item);

        const matches = matchesInventoryItem(item, query);

        assert.equal(matches, true);
        assert.deepEqual(item, before);
    });
}

for (const query of ['ЗЕЛЕНЫЙ', 'зелёный', '  крем   EMANSI  ', 'крем 08.2029', '2345,67', '1\u00a0234,56', '']) {
    test(`inventory search handles words and formatting for ${JSON.stringify(query)}`, () => {
        const item = product();

        const matches = matchesInventoryItem(item, query);

        assert.equal(matches, true);
    });
}

for (const query of ['нет такого товара', 'крем сыворотка', '08.2028', '<script>alert(1)</script>', 'undefined', 'null']) {
    test(`inventory search rejects unrelated values for ${JSON.stringify(query)}`, () => {
        const item = product();

        const matches = matchesInventoryItem(item, query);

        assert.equal(matches, false);
    });
}

test('search preserves long articles and leading zeroes', () => {
    const article = '000012345678901234567890123456789012345678901234567890123456789012';
    const item = product({article});

    const matches = matchesInventoryItem(item, article);

    assert.equal(matches, true);
    assert.equal(item.article, article);
});

test('expired and zero-quantity items are searchable without an activity filter', () => {
    const item = product({quantity: '0', expiry: '01.2020', expiry_status: 'expired'});

    const matches = matchesInventoryItem(item, 'EMANSI 01.2020 0');

    assert.equal(matches, true);
});

class Node extends EventTarget {
    constructor(tag = 'input', text = '', className = '') {
        super(); Object.assign(this, {tag, textContent: text, className, children: [], value: '', hidden: false, attributes: {}});
    }
    append(...children) { this.children.push(...children); }
    replaceChildren(...children) { this.children = children; }
    setAttribute(name, value) { this.attributes[name] = value; }
    focus() { this.focused = true; }
}

function searchPage(t, items) {
    const ids = ['product-search', 'product-search-field', 'toggle-product-search', 'clear-product-search', 'products-body'];
    const nodes = Object.fromEntries(ids.map(id => [id, new Node()]));
    nodes['product-search-field'].hidden = true;
    const previousDocument = globalThis.document;
    globalThis.document = {getElementById: id => nodes[id]};
    t.after(() => {
        if (previousDocument === undefined) delete globalThis.document;
        else globalThis.document = previousDocument;
    });
    const page = Object.create(InventoryPage.prototype);
    page.items = new Map(items.map(item => [item.id, item]));
    page.element = (tag, text, className) => new Node(tag, text, className);
    page.productRow = item => ({item});
    page.request = () => assert.fail('Typing must not send requests or change stock');
    page.bindSearch();
    page.renderProducts();
    return {page, nodes, input: nodes['product-search'], field: nodes['product-search-field'],
        toggle: nodes['toggle-product-search'], clear: nodes['clear-product-search'],
        shown: () => nodes['products-body'].children.flatMap(node => node.item ? [node.item] : []),
        type(query) { this.input.value = query; this.input.dispatchEvent(new Event('input')); }};
}

test('magnifier opens the hidden field and focuses it', t => {
    const ui = searchPage(t, [product()]);

    ui.toggle.dispatchEvent(new Event('click'));

    assert.equal(ui.field.hidden, false);
    assert.equal(ui.toggle.attributes['aria-expanded'], 'true');
    assert.equal(ui.input.focused, true);
});

test('input searches every item including the last one and retains the complete catalogue', t => {
    const items = Array.from({length: 150}, (_, index) => product({id: index + 1}));
    items.push(product({id: 151, article: '008450', name: 'Маска после процедур'}));
    const before = structuredClone(items);
    const ui = searchPage(t, items);

    ui.type('маска процедур');

    assert.deepEqual(ui.shown().map(item => item.id), [151]);
    assert.equal(ui.page.items.size, 151);
    assert.deepEqual([...ui.page.items.values()], before);
});

test('failed search shows an empty state and clearing restores all rows', t => {
    const items = [product(), product({id: 2, name: 'Сыворотка'})];
    const ui = searchPage(t, items);
    ui.type('нет совпадений');
    const emptyMessage = ui.nodes['products-body'].children[0].children[0].textContent;

    ui.clear.dispatchEvent(new Event('click'));

    assert.equal(emptyMessage, 'Ничего не найдено');
    assert.deepEqual(ui.shown(), items);
    assert.equal(ui.input.value, '');
    assert.equal(ui.clear.hidden, true);
    assert.equal(ui.input.focused, true);
});

test('second magnifier click closes the field and resets the filter', t => {
    const items = [product(), product({id: 2, name: 'Маска'})];
    const ui = searchPage(t, items);
    ui.toggle.dispatchEvent(new Event('click'));
    ui.type('маска');

    ui.toggle.dispatchEvent(new Event('click'));

    assert.equal(ui.field.hidden, true);
    assert.equal(ui.toggle.attributes['aria-expanded'], 'false');
    assert.equal(ui.input.value, '');
    assert.deepEqual(ui.shown(), items);
});

test('Escape closes search, resets the filter and focuses the magnifier', t => {
    const ui = searchPage(t, [product()]);
    ui.toggle.dispatchEvent(new Event('click'));
    ui.type('нет совпадений');
    const event = new Event('keydown', {cancelable: true});
    Object.defineProperty(event, 'key', {value: 'Escape'});

    ui.input.dispatchEvent(event);

    assert.equal(event.defaultPrevented, true);
    assert.equal(ui.field.hidden, true);
    assert.equal(ui.input.value, '');
    assert.equal(ui.shown().length, 1);
    assert.equal(ui.toggle.focused, true);
});

test('sorting or editing refresh keeps the query and filters the latest response', async t => {
    const ui = searchPage(t, [product()]);
    ui.type('маска');
    const updated = product({name: 'Маска для лица'});
    ui.page.refreshVersion = 0;
    ui.page.sortField = 'brand';
    ui.page.descending = true;
    ui.page.request = async url => {
        assert.equal(url, '/inventory/items?sort=brand&descending=true');
        return {items: [updated]};
    };

    await ui.page.refresh();

    assert.equal(ui.input.value, 'маска');
    assert.deepEqual(ui.shown(), [updated]);
});

test('quantity changes are included in the next search render', t => {
    const item = product(), ui = searchPage(t, [item]);
    ui.type('19');
    const initiallyShown = ui.shown().length;
    ui.page.items.set(item.id, {...item, quantity: '20'});

    ui.page.renderProducts();

    assert.equal(initiallyShown, 1);
    assert.equal(ui.shown().length, 0);
    assert.equal(ui.input.value, '19');
});
