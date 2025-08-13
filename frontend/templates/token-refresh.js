// Обновление токена каждые 25 минут
setInterval(async () => {
    try {
        const response = await fetch('/refresh', {
            method: 'POST',
            credentials: 'same-origin'
        });
        if (response.ok) {
            console.log('Token refreshed successfully');
        }
    } catch (error) {
        console.error('Error refreshing token:', error);
    }
}, 25 * 60 * 1000);
