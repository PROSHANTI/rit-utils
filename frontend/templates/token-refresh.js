async function checkAndRefreshToken() {
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
}

document.addEventListener('DOMContentLoaded', checkAndRefreshToken);
