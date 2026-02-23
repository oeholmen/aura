const CACHE_NAME = 'aura-v7-hardened';
const ASSETS_TO_CACHE = [
  '/',
  '/static/aura.css',
  '/static/manifest.json',
  '/static/icon.svg',
  '/static/icon-192.png',
  '/static/icon-512.png',
  '/static/aura.js',
  '/static/service-worker.js'
];

// ── Install: Cache core assets ──
self.addEventListener('install', (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      console.log('[Aura SW] Caching app shell');
      return cache.addAll(ASSETS_TO_CACHE);
    })
  );
});

// ── Activate: Clean old caches, claim clients ──
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keyList) => {
      return Promise.all(keyList.map((key) => {
        if (key !== CACHE_NAME) {
          console.log('[Aura SW] Removing old cache', key);
          return caches.delete(key);
        }
      }));
    }).then(() => self.clients.claim())
  );
});

// ── Fetch: Network-first with cache fallback ──
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET') return;
  if (url.pathname.startsWith('/ws/')) return;
  if (url.pathname.startsWith('/api/')) return;

  event.respondWith(
    fetch(event.request)
      .then((response) => {
        if (response.ok) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
        }
        return response;
      })
      .catch(() => caches.match(event.request))
  );
});

// ── Push Notifications (from page via postMessage) ──
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'AURA_REPLY') {
    const { title, body, tag } = event.data;
    // Only notify if no visible client is focused
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clients) => {
      const anyFocused = clients.some(c => c.focused || c.visibilityState === 'visible');
      if (!anyFocused) {
        self.registration.showNotification(title || 'Aura', {
          body: body || 'New message',
          icon: '/icon-192.png',
          badge: '/icon-192.png',
          tag: tag || 'aura-reply',
          renotify: true,
          vibrate: [100, 50, 100],
          data: { url: '/' },
          actions: [
            { action: 'open', title: 'Open Aura' },
            { action: 'dismiss', title: 'Dismiss' }
          ]
        });
      }
    });
  }

  // v5.1: Background mode — persistent notification keeps Aura alive
  if (event.data && event.data.type === 'AURA_BACKGROUND_MODE') {
    const enabled = event.data.enabled;
    if (enabled) {
      self.registration.showNotification('Aura is running', {
        body: 'Aura is active in the background. Tap to open.',
        icon: '/icon-192.png',
        badge: '/icon-192.png',
        tag: 'aura-background',
        silent: true,
        requireInteraction: true,
        data: { url: '/', background: true },
        actions: [
          { action: 'open', title: 'Open' },
          { action: 'stop', title: 'Stop Background' }
        ]
      });
    } else {
      // Close the persistent notification
      self.registration.getNotifications({ tag: 'aura-background' }).then(notifications => {
        notifications.forEach(n => n.close());
      });
    }
  }
});

// ── Notification click → focus or open app ──
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  if (event.action === 'dismiss') return;

  // v5.1: Stop background mode
  if (event.action === 'stop') {
    self.registration.getNotifications({ tag: 'aura-background' }).then(ns => ns.forEach(n => n.close()));
    return;
  }

  event.waitUntil(
    self.clients.matchAll({ type: 'window' }).then((clients) => {
      // Focus existing window if any
      for (const client of clients) {
        if ('focus' in client) return client.focus();
      }
      // Otherwise open new
      return self.clients.openWindow(event.notification.data?.url || '/');
    })
  );
});

// ── Background Sync: reconnect WebSocket when back online ──
self.addEventListener('sync', (event) => {
  if (event.tag === 'aura-reconnect') {
    event.waitUntil(
      fetch('/api/state').then(r => r.json()).then(data => {
        console.log('[Aura SW] Background sync — server alive, cycle:', data.cycle);
      }).catch(() => {
        console.log('[Aura SW] Background sync — server unreachable');
      })
    );
  }
});

// ── Periodic Background Sync (keeps connection alive) ──
self.addEventListener('periodicsync', (event) => {
  if (event.tag === 'aura-heartbeat') {
    event.waitUntil(
      fetch('/api/state').then(r => r.json()).then(data => {
        console.log('[Aura SW] Heartbeat — cycle:', data.cycle);
      })
    );
  }
});

