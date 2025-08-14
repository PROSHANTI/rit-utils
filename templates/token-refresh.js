async function checkAndRefreshToken() {
    try {
        const response = await fetch('/refresh', {
            method: 'POST',
            credentials: 'same-origin'
        });
        if (response.ok) {
            console.log('Token refreshed successfully');
            return true;
        }
        return false;
    } catch (error) {
        console.error('Error refreshing token:', error);
        return false;
    }
}

function setupTokenRefresh() {
    setInterval(checkAndRefreshToken, 10 * 60 * 1000);
    const originalFetch = window.fetch;
    window.fetch = async function(url, options = {}) {
        const response = await originalFetch(url, options);``
        if (response.status === 401) {
            const refreshed = await checkAndRefreshToken();
            if (refreshed) {
                return originalFetch(url, options);
            } else {
                window.location.href = '/';
            }
        }
        return response;
    };
}

document.addEventListener('DOMContentLoaded', function() {
    checkAndRefreshToken();
    setupTokenRefresh();
});
