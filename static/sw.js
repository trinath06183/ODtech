// ODtech BOM Tracker — Service Worker
// Caches core static assets for fast offline/repeat loads

const CACHE_NAME = 'odtech-bom-v1';
const STATIC_ASSETS = [
  '/',
  '/static/manifest.json',
];

// Install: cache core assets
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      return cache.addAll(STATIC_ASSETS).catch(() => {
        // Don't fail install if some assets are unavailable
      });
    })
  );
  self.skipWaiting();
});

// Activate: clean up old caches
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys
          .filter(key => key !== CACHE_NAME)
          .map(key => caches.delete(key))
      )
    )
  );
  self.clients.claim();
});

// Fetch: Network-first strategy for HTML (always fresh),
// Cache-first for static assets (fast repeat loads)
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  // Skip non-GET, cross-origin, and API requests
  if (
    event.request.method !== 'GET' ||
    !url.origin.startsWith(self.location.origin) ||
    url.pathname.startsWith('/api/') ||
    url.pathname.startsWith('/admin/')
  ) {
    return;
  }

  // Static assets: cache-first
  if (
    url.pathname.startsWith('/static/') ||
    url.pathname.startsWith('/media/')
  ) {
    event.respondWith(
      caches.match(event.request).then(cached => {
        if (cached) return cached;
        return fetch(event.request).then(response => {
          if (response.ok) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
          }
          return response;
        });
      })
    );
    return;
  }

  // Everything else: network-first (always fresh data)
  event.respondWith(
    fetch(event.request).catch(() => caches.match(event.request))
  );
});
