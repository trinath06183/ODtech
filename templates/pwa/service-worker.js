const CACHE_NAME = 'odtech-erp-cache-v2';
const urlsToCache = [
  '/',
  '/documents/offline/',
  '/static/img/logo.png',
  '/static/vendor/css/fonts.css',
  '/static/vendor/js/tailwindcss.js'
];

self.addEventListener('install', function(event) {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(function(cache) {
        return cache.addAll(urlsToCache.map(url => new Request(url, { mode: 'no-cors' })));
      })
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('fetch', function(event) {
  if (event.request.method !== 'GET') return;

  event.respondWith(
    fetch(event.request)
      .then(function(response) {
        if (event.request.url.includes('/documents/offline/')) {
          const resClone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, resClone));
        }
        return response;
      })
      .catch(async function() {
        // When offline / server down:
        // 1. If requesting exact resource from cache
        const cached = await caches.match(event.request);
        if (cached && !event.request.url.endsWith('/') && event.request.mode !== 'navigate') {
          return cached;
        }

        // 2. If navigating or loading root while server is down -> Route directly to Offline Document Creator!
        if (event.request.mode === 'navigate' || event.request.url.endsWith(':8000/') || event.request.url.endsWith(':8000')) {
          const offlinePage = await caches.match('/documents/offline/');
          if (offlinePage) return offlinePage;
        }

        return cached || new Response('Offline. Please visit /documents/offline/', { status: 503 });
      })
  );
});

self.addEventListener('activate', function(event) {
  var cacheWhitelist = [CACHE_NAME];
  event.waitUntil(
    caches.keys().then(function(cacheNames) {
      return Promise.all(
        cacheNames.map(function(cacheName) {
          if (cacheWhitelist.indexOf(cacheName) === -1) {
            return caches.delete(cacheName);
          }
        })
      );
    })
  );
});
