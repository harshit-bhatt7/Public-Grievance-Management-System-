self.addEventListener('push', (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch (_) {}
  const title = data.title || 'Public Grievance Management System';
  const options = { body: data.message || 'You have a new notification.', data: { url: data.url || '/' } };
  event.waitUntil(self.registration.showNotification(title, options));
});
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = event.notification.data?.url || '/';
  event.waitUntil(clients.matchAll({type: 'window', includeUncontrolled: true}).then((clientList) => {
    for (const client of clientList) {
      if ('focus' in client) { client.navigate(url); return client.focus(); }
    }
    if (clients.openWindow) return clients.openWindow(url);
  }));
});
