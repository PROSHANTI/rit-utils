(() => {
    const updateVisibility = () => {
        document.documentElement.classList.toggle('page-paused', document.hidden);
    };
    document.addEventListener('visibilitychange', updateVisibility);
    updateVisibility();
})();
