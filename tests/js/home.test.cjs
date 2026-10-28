const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const { LoveNoteDeck, CatPhotoLoader, wishes, affections, total, storageKey } = require('../../templates/home.js');

test('the shared background pauses initially and resumes when the page becomes visible', () => {
    const classes = new Set(), listeners = new Map();
    const document = {
        hidden: true,
        documentElement: { classList: { toggle: (name, enabled) => enabled ? classes.add(name) : classes.delete(name) } },
        addEventListener: (name, callback) => listeners.set(name, callback),
    };
    const source = fs.readFileSync(path.join(__dirname, '../../templates/ambient_background.js'), 'utf8');
    vm.runInNewContext(source, { document });
    const initiallyPaused = classes.has('page-paused');

    document.hidden = false;
    listeners.get('visibilitychange')();

    assert.equal(initiallyPaused, true);
    assert.equal(classes.has('page-paused'), false);
});

function memoryStorage() {
    const values = new Map();
    return { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value) };
}

function loginCountdown(seconds) {
    const password = { disabled: true }, button = { disabled: true }, listeners = new Map(), timers = new Map();
    const countdown = { dataset: { seconds: String(seconds) }, textContent: '', parentElement: { textContent: '' } };
    let now = 0, timer = 0;
    const document = {
        getElementById: id => id === 'login-cooldown' ? countdown : password,
        querySelector: () => button,
        addEventListener: (name, callback) => listeners.set(name, callback),
        removeEventListener: name => listeners.delete(name),
    };
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../../templates/login.js'), 'utf8'), {
        document,
        Date: { now: () => now },
        setTimeout: callback => { timers.set(++timer, callback); return timer; },
        clearTimeout: id => timers.delete(id),
    });
    return {
        password, button, countdown, listeners, timers,
        advance: milliseconds => { now += milliseconds; },
        tick: () => [...timers.values()][0](),
    };
}

test('the login countdown keeps the last second blocked and unlocks exactly after five minutes', () => {
    const ui = loginCountdown(300);
    const initialText = ui.countdown.textContent;

    ui.advance(299001);
    ui.tick();
    const beforeExpiry = { disabled: ui.button.disabled, text: ui.countdown.textContent };
    ui.advance(999);
    ui.tick();

    assert.equal(initialText, '05:00');
    assert.deepEqual(beforeExpiry, { disabled: true, text: '00:01' });
    assert.equal(ui.password.disabled, false);
    assert.equal(ui.button.disabled, false);
    assert.equal(ui.countdown.parentElement.textContent, 'Можно попробовать снова.');
    assert.equal(ui.timers.size, 0);
});

test('returning to a suspended login tab refreshes the countdown without waiting for old timer ticks', () => {
    const ui = loginCountdown(300);

    ui.advance(301000);
    ui.listeners.get('visibilitychange')();

    assert.equal(ui.button.disabled, false);
    assert.equal(ui.password.disabled, false);
    assert.equal(ui.listeners.size, 0);
    assert.equal(ui.timers.size, 0);
});

test('an unblocked login page does not start a countdown', () => {
    const getElementById = () => null;
    const unexpected = () => { throw new Error('no cooldown is rendered'); };
    const source = fs.readFileSync(path.join(__dirname, '../../templates/login.js'), 'utf8');

    assert.doesNotThrow(() => vm.runInNewContext(source, {
        document: { getElementById, querySelector: unexpected, addEventListener: unexpected },
        setTimeout: unexpected,
    }));
});

const settle = () => new Promise(resolve => setImmediate(resolve));

function catLoader(options = {}) {
    const images = [], shown = [], timers = new Map(), busy = [];
    let fallback = 0, request = 0, timer = 0;
    const loader = new CatPhotoLoader({
        createImage: () => {
            const image = { naturalWidth: 400, removeAttribute(name) { delete this[name]; } };
            images.push(image);
            return image;
        },
        requestUrl: async () => `https://mimimi.ru/content/${++request}.jpg`,
        onImage: image => shown.push(image),
        onFallback: () => fallback++,
        onBusy: value => busy.push(value),
        setTimer: fn => { timers.set(++timer, fn); return timer; },
        clearTimer: id => timers.delete(id),
        ...options,
    });
    return { loader, images, shown, timers, busy, fallback: () => fallback };
}

test('all 1600 complete messages are unique and contain no long dashes', () => {
    const deck = new LoveNoteDeck(memoryStorage());

    const messages = Array.from({ length: total }, () => deck.next());

    assert.equal(wishes.length, 40);
    assert.equal(affections.length, 40);
    assert.equal(new Set(messages).size, 1600);
    assert.ok(messages.every(message => !/[\u2013\u2014]/.test(message)));
});

test('reloads and alternating tabs continue the same saved deck', () => {
    const storage = memoryStorage(), shown = new Set();
    const first = new LoveNoteDeck(storage), second = new LoveNoteDeck(storage);

    for (let i = 0; i < 100; i++) shown.add((i % 2 ? first : second).next());
    for (let i = 0; i < 100; i++) shown.add(new LoveNoteDeck(storage).next());

    assert.equal(shown.size, 200);
    assert.equal(JSON.parse(storage.getItem(storageKey)).remaining.length, 1400);
});

test('a new cycle does not immediately repeat the previous message', () => {
    const deck = new LoveNoteDeck(null, () => 0);
    let previous;
    for (let i = 0; i < total; i++) previous = deck.next();

    const message = deck.next();

    assert.notEqual(message, previous);
});

test('blocked storage keeps nonrepeating messages available on the current page', () => {
    const storage = { getItem() { throw new Error('blocked'); }, setItem() { throw new Error('full'); } };
    const deck = new LoveNoteDeck(storage);

    const messages = Array.from({ length: 100 }, () => deck.next());

    assert.equal(new Set(messages).size, 100);
});

test('malformed saved data is recovered without putting untrusted text into messages', () => {
    const storage = memoryStorage();
    const invalid = ['{broken', 'null', '{"version":1,"remaining":[1,1],"last":-1}', '{"version":1,"remaining":[9999],"last":-1}'];

    const messages = invalid.map(value => { storage.setItem(storageKey, value); return new LoveNoteDeck(storage).next(); });

    assert.ok(messages.every(message => wishes.some(wish => message.startsWith(wish))));
});

test('the next photograph is prepared in advance and swapped synchronously', async () => {
    const { loader, images, shown, busy } = catLoader();

    loader.load();
    await settle();
    images[0].onload();
    await settle();
    images[1].onload();
    loader.load();

    assert.deepEqual(shown, [images[0], images[1]]);
    assert.equal(images[0].referrerPolicy, 'no-referrer');
    assert.ok(busy.includes(false));
    loader.cancel();
});

test('explicit preparation buffers one photograph without showing it', async () => {
    const { loader, images, shown } = catLoader();

    assert.equal(images.length, 0);
    await loader.prepare();
    await settle();
    images[0].onload();
    await settle();
    await loader.prepare();

    assert.equal(images.length, 1);
    assert.equal(shown.length, 0);
    loader.load();
    assert.equal(shown[0], images[0]);
    loader.cancel();
});

test('timeout falls back and ignores a late source response', async () => {
    let respond;
    const pendingUrl = new Promise(resolve => { respond = resolve; });
    const context = catLoader({ requestUrl: () => pendingUrl });

    context.loader.load();
    [...context.timers.values()][0]();
    respond('https://mimimi.ru/content/123.jpg');
    await settle();

    assert.equal(context.fallback(), 1);
    assert.equal(context.images.length, 0);
    assert.equal(context.busy.at(-1), false);
});

test('an unavailable source uses the local photograph and restores the button', async () => {
    const context = catLoader({ requestUrl: async () => { throw new Error('offline'); } });

    context.loader.load();
    await settle();

    assert.equal(context.fallback(), 1);
    assert.equal(context.busy.at(-1), false);
    assert.equal(context.timers.size, 0);
});

test('closing the dialog cancels loading and ignores late image events', async () => {
    const context = catLoader();
    context.loader.load();
    await settle();
    const lateLoad = context.images[0].onload;

    context.loader.cancel();
    lateLoad();

    assert.equal(context.shown.length, 0);
    assert.equal(context.timers.size, 0);
    assert.equal(context.busy.at(-1), false);
});

test('unsafe image URLs are rejected before creating a network image', async () => {
    const context = catLoader({ requestUrl: async () => 'https://mimimi.ru.evil.test/content/1.jpg' });

    context.loader.load();
    await settle();

    assert.equal(context.images.length, 0);
    assert.equal(context.fallback(), 1);
});

test('default timers retain their browser receiver', async () => {
    const source = fs.readFileSync(path.join(__dirname, '../../templates/home.js'), 'utf8');
    const sandbox = { module: { exports: {} }, AbortController };
    vm.runInNewContext(`
        function setTimeout() { if (this !== globalThis) throw new TypeError('Illegal invocation'); return 1; }
        function clearTimeout() { if (this !== globalThis) throw new TypeError('Illegal invocation'); }
        ${source}
    `, sandbox);
    const loader = new sandbox.module.exports.CatPhotoLoader({
        createImage: () => ({ removeAttribute() {} }), requestUrl: async () => 'https://mimimi.ru/content/1.jpg',
        onImage() {}, onFallback() {}, onBusy() {},
    });

    await loader.prepare();
    loader.cancel();

    assert.equal(loader.pending, null);
});
