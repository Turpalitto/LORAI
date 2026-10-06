/* LORAI Service Worker: app-shell cache-first + SWR для чтения протоколов.
   Версионирование через имя кэша: bump CACHE при изменении шелла. */
const STATIC_CACHE = 'lorai-static-v1';
const API_CACHE = 'lorai-api-v1';
const SHELL = ['/', '/index.html', '/manifest.webmanifest', '/icon-192.png', '/icon-512.png', '/offline.html'];
const API_RE = /\/(protocols|checklist|templates)(\/|$|\?)/;

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(STATIC_CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== STATIC_CACHE && k !== API_CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

async function swr(request, cacheName) {
  const cache = await caches.open(cacheName);
  const hit = await cache.match(request);
  const net = fetch(request).then((res) => {
    if (res && res.ok) cache.put(request, res.clone());
    return res;
  }).catch(() => hit);
  return hit || net;
}

self.addEventListener('fetch', (e) => {
  const { request } = e;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (request.mode === 'navigate') {
    e.respondWith(fetch(request).catch(() => caches.match('/index.html').then((r) => r || caches.match('/offline.html'))));
    return;
  }
  if (url.origin === self.location.origin) {
    e.respondWith(swr(request, STATIC_CACHE));
    return;
  }
  if (API_RE.test(url.pathname)) {
    e.respondWith(swr(request, API_CACHE));
  }
});
