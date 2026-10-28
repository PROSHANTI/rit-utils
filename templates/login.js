(() => {
    const countdown = document.getElementById('login-cooldown');
    if (!countdown) return;

    const password = document.getElementById('password');
    const button = document.querySelector('button[type="submit"]');
    const deadline = Date.now() + Number(countdown.dataset.seconds) * 1000;
    let timer;

    const update = () => {
        clearTimeout(timer);
        const remaining = Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
        if (remaining === 0) {
            password.disabled = false;
            button.disabled = false;
            countdown.parentElement.textContent = 'Можно попробовать снова.';
            document.removeEventListener('visibilitychange', update);
            return;
        }
        countdown.textContent = `${String(Math.floor(remaining / 60)).padStart(2, '0')}:${String(remaining % 60).padStart(2, '0')}`;
        timer = setTimeout(update, 1000);
    };

    document.addEventListener('visibilitychange', update);
    update();
})();
