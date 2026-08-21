const CACHE_NAME = 'odtech-offline-v1';
const OFFLINE_URLS = [
  '/',
  '/documents/offline/',
  '/static/img/logo.png',
  '/static/img/stamp.png',
  '/static/img/sign.png',
  '/static/img/phone.png',
  '/static/img/email.png',
  '/static/img/location.png',
  'https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js',
  'https://cdn.tailwindcss.com',
  'https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(OFFLINE_URLS.map(url => new Request(url, { mode: 'no-cors' })));
    }).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME) {
            return caches.delete(key);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;

  event.respondWith(
    fetch(event.request)
      .then((response) => {
        // If online and loading offline page, cache the latest version
        if (event.request.url.includes('/documents/offline/')) {
          const resClone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, resClone));
        }
        return response;
      })
      .catch(async () => {
        // Network failed (server offline / no internet)
        const cachedResponse = await caches.match(event.request);
        if (cachedResponse) return cachedResponse;

        // If it's a page navigation, return the cached offline document generator
        if (event.request.mode === 'navigate') {
          const offlinePage = await caches.match('/documents/offline/');
          if (offlinePage) return offlinePage;
        }

        return new Response('Server Offline. Please open /documents/offline/ from your browser cache.', {
          status: 503,
          statusText: 'Service Unavailable'
        });
      })
  );
});
