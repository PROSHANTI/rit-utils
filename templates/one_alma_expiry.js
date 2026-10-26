(function () {
    'use strict';
    function moscowDay(now = new Date()) {
        const parts = new Intl.DateTimeFormat('en-CA', {timeZone: 'Europe/Moscow', year: 'numeric', month: '2-digit', day: '2-digit'}).formatToParts(now);
        const values = Object.fromEntries(parts.map(part => [part.type, Number(part.value)]));
        return [values.year, values.month, values.day];
    }
    function utcDay(year, month, day) {
        const date = new Date(0);
        date.setUTCFullYear(year, month - 1, day);
        date.setUTCHours(0, 0, 0, 0);
        return date;
    }
    function getExpiryInfo(expiry, now = new Date()) {
        if (!/^(0[1-9]|1[0-2])\.[0-9]{4}$/.test(expiry)) return null;
        const [month, year] = expiry.split('.').map(Number);
        if (year < 1) return null;
        const [currentYear, currentMonth, currentDay] = moscowDay(now);
        const end = utcDay(year, month + 1, 0);
        const warningMonth = utcDay(currentYear, currentMonth + 2, 1);
        const warningLast = utcDay(warningMonth.getUTCFullYear(), warningMonth.getUTCMonth() + 2, 0).getUTCDate();
        const warningUntil = utcDay(warningMonth.getUTCFullYear(), warningMonth.getUTCMonth() + 1, Math.min(currentDay, warningLast));
        const today = utcDay(currentYear, currentMonth, currentDay);
        const daysRemaining = Math.round((end - today) / 86400000);
        return {expiresOn: `${String(end.getUTCDate()).padStart(2, '0')}.${expiry}`, daysRemaining,
            status: daysRemaining < 0 ? 'expired' : end <= warningUntil ? 'soon' : 'normal'};
    }
    function refresh(rows) {
        for (const row of rows) {
            const expiry = row.dataset.expiry || (row.dataset.cells ? JSON.parse(row.dataset.cells)[4] : '');
            const info = getExpiryInfo(expiry);
            row.classList.toggle('expiry-expired', info?.status === 'expired');
            row.classList.toggle('expiry-soon', info?.status === 'soon');
            const cell = row.querySelector('.expiry-cell');
            if (cell) cell.title = !info ? 'Срок не указан' : info.status === 'expired'
                ? `Годен до ${info.expiresOn} включительно. Просрочено: ${-info.daysRemaining} дн.`
                : `Годен до ${info.expiresOn} включительно. Осталось: ${info.daysRemaining} дн.`;
        }
    }
    const api = {getExpiryInfo, moscowDay, refresh};
    if (typeof module !== 'undefined' && module.exports) module.exports = api;
    else {
        window.OneAlmaExpiry = api;
        const start = () => {
            let lastDay = '';
            const update = () => {
                const day = moscowDay().join('-');
                if (day === lastDay) return;
                lastDay = day;
                refresh(document.querySelectorAll('.inventory-table tbody tr'));
            };
            update();
            setInterval(update, 60000);
            document.addEventListener('visibilitychange', () => { if (!document.hidden) update(); });
            window.addEventListener('focus', update);
        };
        if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, {once: true});
        else start();
    }
}());
