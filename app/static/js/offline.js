// this drive me crazy
if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
        navigator.serviceWorker.register('/static/sw.js');
    });
}
let offlineSales = JSON.parse(localStorage.getItem('offlineSales')) || [];
window.addEventListener('online', () => {
    if (offlineSales.length > 0) {
        fetch('/api/sync', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({sales: offlineSales})
        }).then(res => res.json()).then(data => {
            if (data.status === 'success') {
                localStorage.removeItem('offlineSales');
                offlineSales = [];
                alert('Data zote zimesawazishwa!');
            }
        });
    }
});
