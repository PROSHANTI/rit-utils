const assert = require('node:assert/strict');
const {test} = require('node:test');
const {InventoryPage} = require('../../templates/inventory.js');

function page() {
    const inventory = Object.create(InventoryPage.prototype);
    inventory.csrf = 'session-csrf';
    return inventory;
}

test('inventory sends one authenticated edit and accepts the saved response', async t => {
    const calls = [];
    const inventory = page();
    t.mock.method(globalThis, 'fetch', async (...args) => {
        calls.push(args);
        return Response.json({detail: 'Сохранено.'});
    });

    const result = await inventory.request('/inventory/products/1', 'PUT', {quantity: 7});

    assert.equal(result.detail, 'Сохранено.');
    assert.equal(calls.length, 1);
    assert.equal(calls[0][1].headers.Accept, 'application/json');
    assert.equal(calls[0][1].headers['X-CSRF-Token'], 'session-csrf');
    assert.equal(calls[0][1].credentials, 'same-origin');
    assert.deepEqual(JSON.parse(calls[0][1].body), {quantity: 7});
});

test('redirect to login cannot be mistaken for a successful edit', async t => {
    const inventory = page();
    t.mock.method(globalThis, 'fetch', async () => ({status: 200, redirected: true}));

    const request = inventory.request('/inventory/products/1', 'PUT', {quantity: 7});

    await assert.rejects(request, /Сессия завершена/);
});

test('HTML response cannot be mistaken for a successful edit', async t => {
    const inventory = page();
    t.mock.method(globalThis, 'fetch', async () => new Response('<form>Войти</form>', {
        headers: {'Content-Type': 'text/html'},
    }));

    const request = inventory.request('/inventory/products/1', 'PUT', {quantity: 7});

    await assert.rejects(request, /не подтвердил сохранение/);
});

test('malformed JSON cannot be mistaken for a successful edit', async t => {
    const inventory = page();
    t.mock.method(globalThis, 'fetch', async () => new Response('{broken', {
        headers: {'Content-Type': 'application/json'},
    }));

    const request = inventory.request('/inventory/products/1', 'PUT', {quantity: 7});

    await assert.rejects(request, /не подтвердил сохранение/);
});

test('expired session keeps the edit form open and enables another attempt', async t => {
    const inventory = page();
    const button = {disabled: false};
    const dialog = {open: true, close() { this.open = false; }};
    const errors = [];
    const event = {preventDefault() {}, currentTarget: {querySelector() { return button; }}};
    inventory.error = (id, text) => errors.push(text);
    inventory.refresh = () => assert.fail('Failed edit must not reload the table');
    t.mock.method(globalThis, 'fetch', async () => Response.json({detail: 'Войдите снова.'}, {status: 401}));
    const previousDocument = globalThis.document;
    globalThis.document = {getElementById() { return dialog; }};
    t.after(() => {
        if (previousDocument === undefined) delete globalThis.document;
        else globalThis.document = previousDocument;
    });

    await inventory.submit(event, 'product-dialog', () => inventory.request('/inventory/products/1', 'PUT', {quantity: 7}));

    assert.equal(dialog.open, true);
    assert.equal(button.disabled, false);
    assert.match(errors.at(-1), /Введённые данные оставлены в форме/);
});
