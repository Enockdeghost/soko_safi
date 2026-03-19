const CACHE_NAME = 'soko-safi-v1';
const urlsToCache = ['/', '/static/css/style.css', '/static/js/main.js', '/offline.html'];
self.addEventListener('install', event => {
    event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(urlsToCache)));
});
self.addEventListener('fetch', event => {
    event.respondWith(caches.match(event.request).then(response => response || fetch(event.request)));
});