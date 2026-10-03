/* Lecture hors ligne : on essaie toujours le réseau d'abord (données fraîches),
   et on se rabat sur la dernière copie enregistrée si le réseau ne répond pas.
   Seuls les fichiers du site sont concernés (pas GitHub, pas Google Drive). */
const CACHE = 'mpsi-ddl-v1';
const COQUILLE = ['./', 'index.html', 'style.css', 'app.js', 'manifest.webmanifest', 'icone.svg'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(COQUILLE)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys()
    .then((cles) => Promise.all(cles.filter((c) => c !== CACHE).map((c) => caches.delete(c))))
    .then(() => self.clients.claim()));
});

self.addEventListener('fetch', (e) => {
  const requete = e.request;
  if (requete.method !== 'GET' || new URL(requete.url).origin !== self.location.origin) return;
  e.respondWith(
    fetch(requete)
      .then((reponse) => {
        if (reponse.ok) {
          const copie = reponse.clone();
          caches.open(CACHE).then((c) => c.put(requete, copie));
        }
        return reponse;
      })
      .catch(() => caches.match(requete, { ignoreSearch: true })
        .then((r) => r || caches.match('index.html'))),
  );
});
