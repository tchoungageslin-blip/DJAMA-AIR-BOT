// Minimal service worker — required for PWA installability
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()));
// Passthrough fetch — no caching, just enables the install prompt
self.addEventListener('fetch', (e) => e.respondWith(fetch(e.request)));
