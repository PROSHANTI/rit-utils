(() => {
    'use strict';

    const wishes = Object.freeze([
        'Хорошего тебе дня, солнышко.',
        'Пусть сегодня у тебя будет побольше поводов улыбнуться.',
        'Котёнок, пусть этот день будет к тебе добрым.',
        'Желаю тебе сегодня лёгкости и маленьких чудес.',
        'Кит, пусть всё сложится даже лучше, чем ты задумала.',
        'Пусть сегодня найдётся время на что-нибудь приятное только для тебя.',
        'Солнышко, пусть твой чай будет тёплым, а день уютным.',
        'Пусть у тебя сегодня получится то, чего очень хочется.',
        'Котёнок, если день окажется непростым, помни: я всегда на твоей стороне.',
        'Пусть сегодня будет меньше суеты и больше хорошего.',
        'Пусть кто-нибудь сегодня порадует тебя так же, как ты радуешь меня.',
        'Кит, не забывай сегодня беречь себя.',
        'Пусть сегодня будет повод сказать: «Какой хороший день».',
        'Пусть рядом будут добрые люди, а на душе будет спокойно.',
        'Солнышко, желаю тебе сегодня хоть немного времени никуда не спешить.',
        'Пусть сегодняшние заботы окажутся легче, чем кажутся.',
        'Котёнок, пусть сегодня случится что-нибудь по-настоящему милое.',
        'Пусть день принесёт тебе хорошую новость.',
        'Кит, пусть твоя улыбка сегодня появляется сама собой.',
        'Пусть между делами найдётся минутка просто порадоваться.',
        'Желаю тебе сегодня побольше тепла и поменьше усталости.',
        'Пусть сегодня найдётся что-нибудь вкусное и что-нибудь радостное.',
        'Солнышко, пусть сегодняшний день тебя приятно удивит.',
        'Пусть у тебя будет настроение тихонько напевать любимую песню.',
        'Пусть всё важное получается, а лишнее не тревожит.',
        'Пусть сегодня кто-нибудь скажет тебе добрые слова.',
        'Котёнок, пусть этот маленький перерыв подарит тебе улыбку.',
        'Пусть у тебя сегодня будет достаточно сил и на дела, и на себя.',
        'Кит, пусть сегодняшний вечер будет уютным и спокойным.',
        'Пусть сегодня будет больше объятий, чем переживаний.',
        'Пусть день будет мягким, как любимый плед.',
        'Пусть сегодня всё важное получится без лишней спешки.',
        'Солнышко, пусть сегодня найдётся повод побаловать себя.',
        'Пусть этот день оставит после себя что-нибудь светлое.',
        'Пусть даже посреди забот у тебя будет тепло на душе.',
        'Пусть сегодняшний день будет полон маленьких радостей.',
        'Котёнок, пусть сегодня тебе чаще хочется смеяться.',
        'Пусть у тебя всё получается в твоём собственном, удобном ритме.',
        'Пусть в сегодняшнем дне найдётся место твоей мечте.',
        'Пусть этот день станет ещё одним нашим хорошим воспоминанием.',
    ]);

    const affections = Object.freeze([
        'Я тебя очень сильно люблю, кит.',
        'Ты моё счастье, солнышко.',
        'Мне так повезло, что у меня есть ты.',
        'Ты моё самое любимое «вместе».',
        'Очень люблю тебя, мой котёнок.',
        'Ты делаешь мою жизнь теплее одним своим присутствием.',
        'Мне хорошо уже от мысли, что ты у меня есть.',
        'Кит, ты мой самый родной человек.',
        'С тобой даже обычный день становится особенным.',
        'Мне очень хочется сейчас обнять тебя, солнышко.',
        'Твоя улыбка для меня дороже всего на свете.',
        'Я люблю и твой смех, и наши тихие вечера рядом.',
        'Ты моё любимое место, куда всегда хочется возвращаться.',
        'Котёнок, я так счастлив, что мы нашли друг друга.',
        'Ты прекрасна и в нарядном платье, и в самой домашней футболке.',
        'Я люблю тебя и в хорошие дни, и в те, когда всё валится из рук.',
        'Мне не нужен особенный повод, чтобы сказать, как ты мне дорога.',
        'Ты моё самое любимое счастье, кит.',
        'Пусть это маленькое сердечко напомнит, как сильно я тебя люблю.',
        'Я бы снова выбрал тебя. И снова. И ещё раз.',
        'С тобой у меня есть наш маленький, самый уютный мир.',
        'Солнышко, мне нравится идти по жизни именно с тобой.',
        'Я люблю слушать, как ты смеёшься.',
        'Котёнок, ты можешь быть собой. Я люблю тебя настоящую.',
        'Мне дорого всё наше: разговоры, привычки и даже смешные мелочи.',
        'Ты заслуживаешь столько же тепла, сколько даришь другим.',
        'Ты у меня удивительная, и мне хочется напоминать тебе об этом чаще.',
        'Кит, мне очень нравится наша жизнь с тобой.',
        'Я рядом и когда хочется праздновать, и когда хочется просто помолчать.',
        'Ты делаешь слово «дом» таким тёплым.',
        'Мой любимый план на вечер: побыть рядом с тобой.',
        'Я люблю тебя больше, чем умею выразить словами.',
        'Иногда я просто смотрю на тебя и думаю: «Как же мне повезло».',
        'Ты моя любимая девочка, даже когда день совсем взрослый и сложный.',
        'Солнышко, у меня для тебя всегда найдутся объятия.',
        'Спасибо тебе за нас. Мне очень дорого то, что у нас есть.',
        'Рядом с тобой я чувствую себя на своём месте.',
        'Я всё ещё радуюсь твоим сообщениям, как самому первому.',
        'С тобой хочется делиться всем хорошим.',
        'Котёнок, если бы можно было отправить объятие через экран, оно было бы уже у тебя.',
    ]);

    const total = wishes.length * affections.length;
    const storageKey = 'rit.love-notes.v1';

    class LoveNoteDeck {
        constructor(storage, random = Math.random) {
            this.storage = storage;
            this.random = random;
            this.memory = null;
        }

        valid(state) {
            return state?.version === 1 && Array.isArray(state.remaining)
                && state.remaining.length <= total
                && state.remaining.every(id => Number.isInteger(id) && id >= 0 && id < total)
                && new Set(state.remaining).size === state.remaining.length
                && Number.isInteger(state.last) && state.last >= -1 && state.last < total
                && !state.remaining.includes(state.last);
        }

        read() {
            try {
                const state = JSON.parse(this.storage?.getItem(storageKey) ?? 'null');
                if (this.valid(state)) return state;
            } catch { /* Storage can be disabled; keep the current page usable. */ }
            return this.memory ?? this.fresh();
        }

        fresh(last = -1) {
            const remaining = Array.from({ length: total }, (_, i) => i);
            for (let i = remaining.length - 1; i > 0; i--) {
                const j = Math.floor(this.random() * (i + 1));
                [remaining[i], remaining[j]] = [remaining[j], remaining[i]];
            }
            return { version: 1, remaining, last };
        }

        next() {
            let state = this.read();
            if (!state.remaining.length) state = this.fresh(state.last);
            let index = state.remaining.length - 1;
            if (state.last >= 0) {
                const differentParts = id => Math.floor(id / affections.length) !== Math.floor(state.last / affections.length)
                    && id % affections.length !== state.last % affections.length;
                const preferred = state.remaining.findLastIndex(differentParts);
                if (preferred >= 0) index = preferred;
                else if (state.remaining[index] === state.last && index > 0) index--;
            }
            const [id] = state.remaining.splice(index, 1);
            state.last = id;
            this.memory = state;
            try { this.storage?.setItem(storageKey, JSON.stringify(state)); } catch { /* Memory remains available. */ }
            return wishes[Math.floor(id / affections.length)] + ' ' + affections[id % affections.length];
        }
    }

    class CatPhotoLoader {
        constructor({ createImage, requestUrl, onImage, onFallback, onBusy,
            setTimer = (callback, delay) => setTimeout(callback, delay), clearTimer = timer => clearTimeout(timer) }) {
            Object.assign(this, { createImage, requestUrl, onImage, onFallback, onBusy, setTimer, clearTimer });
            this.generation = 0;
            this.pending = null;
            this.timer = null;
            this.ready = null;
            this.controller = null;
            this.displayRequested = false;
        }

        cancel() {
            this.generation++;
            if (this.timer !== null) this.clearTimer(this.timer);
            this.timer = null;
            this.controller?.abort();
            this.controller = null;
            if (this.pending) {
                if (this.pending.image) {
                    this.pending.image.onload = null;
                    this.pending.image.onerror = null;
                    this.pending.image.removeAttribute('src');
                }
            }
            this.pending = null;
            this.displayRequested = false;
            this.onBusy(false);
        }

        load() {
            if (this.ready) {
                this.onImage(this.ready);
                this.ready = null;
            } else {
                this.displayRequested = true;
            }
            this.prepare();
        }

        async prepare() {
            if (this.pending || this.ready) return;
            const generation = ++this.generation;
            const pending = { image: null };
            this.pending = pending;
            this.controller = new AbortController();
            this.onBusy(true);
            const finish = success => {
                if (generation !== this.generation) return;
                this.generation++;
                if (this.timer !== null) this.clearTimer(this.timer);
                this.timer = null;
                this.controller?.abort();
                this.controller = null;
                const image = pending.image;
                if (image) {
                    image.onload = null;
                    image.onerror = null;
                }
                this.pending = null;
                if (success) {
                    if (this.displayRequested) {
                        this.displayRequested = false;
                        this.onImage(image);
                        this.prepare();
                    } else {
                        this.ready = image;
                        this.onBusy(false);
                    }
                } else {
                    image?.removeAttribute('src');
                    if (this.displayRequested) this.onFallback();
                    this.displayRequested = false;
                    this.onBusy(false);
                }
            };
            this.timer = this.setTimer(() => finish(false), 8000);
            try {
                const url = await this.requestUrl(this.controller.signal);
                if (generation !== this.generation) return;
                if (url !== '/static/images/cat-fallback.jpg'
                    && !/^https:\/\/mimimi\.ru\/content\/[a-zA-Z0-9_-]+\.(?:jpe?g|png|webp)$/i.test(url)) {
                    throw new Error('Unexpected cat image URL');
                }
                if (url === '/static/images/cat-fallback.jpg') { finish(false); return; }
                const image = this.createImage();
                pending.image = image;
                image.alt = 'Случайный котик';
                image.referrerPolicy = 'no-referrer';
                image.decoding = 'async';
                image.onload = () => finish(image.naturalWidth > 0);
                image.onerror = () => finish(false);
                image.src = url;
            } catch {
                finish(false);
            }
        }
    }

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = { LoveNoteDeck, CatPhotoLoader, wishes, affections, total, storageKey };
    }
    if (typeof document === 'undefined') return;

    const heart = document.getElementById('love-trigger');
    const note = document.getElementById('love-note');
    if (!heart || !note) return;
    let storage = null;
    try { storage = window.localStorage; } catch { /* Some browsers restrict storage. */ }
    const deck = new LoveNoteDeck(storage);
    const message = document.getElementById('love-message');

    function placeNote() {
        if (note.hidden) return;
        const anchor = heart.getBoundingClientRect();
        const brand = document.querySelector('.brand-wordmark').getBoundingClientRect();
        const middle = anchor.left + anchor.width / 2;
        const left = Math.max(16, Math.min(window.innerWidth - note.offsetWidth - 16, middle - note.offsetWidth / 2));
        note.style.left = `${left}px`;
        note.style.top = `${Math.max(12, Math.min(brand.bottom + 16, window.innerHeight - note.offsetHeight - 16))}px`;
        note.style.setProperty('--love-arrow', `${Math.max(20, Math.min(note.offsetWidth - 20, middle - left))}px`);
    }

    function closeNote(restoreFocus = false) {
        note.hidden = true;
        heart.setAttribute('aria-expanded', 'false');
        if (restoreFocus) heart.focus();
    }

    function nextNote() {
        message.textContent = deck.next();
        placeNote();
    }

    heart.addEventListener('click', () => {
        if (!note.hidden) { closeNote(); return; }
        note.hidden = false;
        heart.setAttribute('aria-expanded', 'true');
        nextNote();
    });
    document.getElementById('love-next').addEventListener('click', nextNote);
    document.getElementById('love-close').addEventListener('click', () => closeNote(true));
    document.addEventListener('click', event => {
        if (!note.hidden && !note.contains(event.target) && !heart.contains(event.target)) closeNote();
    });
    document.addEventListener('keydown', event => {
        if (event.key === 'Escape' && !note.hidden) closeNote(true);
    });
    window.addEventListener('resize', placeNote);
    window.addEventListener('scroll', () => closeNote(), { passive: true });

    const catDialog = document.getElementById('cat-dialog');
    const catFrame = document.getElementById('cat-frame');
    const catNext = document.getElementById('cat-next');
    const loader = new CatPhotoLoader({
        createImage: () => new Image(),
        requestUrl: async signal => {
            const response = await fetch('/home/cat', { signal, cache: 'no-store', credentials: 'same-origin' });
            if (!response.ok) throw new Error('Cat service unavailable');
            const result = await response.json();
            return result.url;
        },
        onImage: image => {
            image.id = 'cat-photo';
            image.className = 'cat-photo';
            document.getElementById('cat-photo').replaceWith(image);
            document.getElementById('cat-placeholder').hidden = true;
        },
        onFallback: () => {
            const image = document.getElementById('cat-photo');
            image.src = '/static/images/cat-fallback.jpg';
            image.alt = 'Наш домашний котик';
            image.className = 'cat-photo cat-fallback';
            image.hidden = false;
            document.getElementById('cat-placeholder').hidden = true;
        },
        onBusy: busy => {
            catNext.disabled = busy;
            catFrame.setAttribute('aria-busy', String(busy));
        },
    });
    document.getElementById('cat-trigger').addEventListener('click', () => {
        closeNote();
        catDialog.showModal();
        loader.load();
    });
    catNext.addEventListener('click', () => loader.load());
    document.getElementById('cat-close').addEventListener('click', () => catDialog.close());
    catDialog.addEventListener('click', event => { if (event.target === catDialog) catDialog.close(); });
    catDialog.addEventListener('close', () => loader.cancel());

    const prepareCat = () => { if (!document.hidden) loader.prepare(); };
    if (typeof window.requestIdleCallback === 'function') {
        window.requestIdleCallback(prepareCat, { timeout: 1200 });
    } else {
        setTimeout(prepareCat, 350);
    }
    document.addEventListener('visibilitychange', prepareCat);
})();
