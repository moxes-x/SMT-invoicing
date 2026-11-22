/* Keeps the app itself (not your data: the app saves that separately) on the phone, so it
 * opens without a connection. Customer pages, the API and the admin always go to the network. */
const VERSION = "v1";
const CACHE = `app-${VERSION}`;
const SHELL = ["/", "/manifest.webmanifest", "/icons/icon-192.png", "/icons/icon-512.png"];
const NETWORK_ONLY = ["/api/", "/i/", "/q/", "/r/", "/admin", "/static/", "/media/"];

// Save the app on first visit: the page, plus the scripts and styles it names (they loaded
// before this worker existed, so they didn't pass through it).
async function saveShell() {
  const cache = await caches.open(CACHE);
  await cache.addAll(SHELL);
  const html = await (await cache.match("/")).text();
  const assets = [...html.matchAll(/(?:src|href)="(\/assets\/[^"]+)"/g)].map((m) => m[1]);
  await cache.addAll(assets);
}

self.addEventListener("install", (event) => {
  event.waitUntil(saveShell().then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  const url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== self.location.origin) return;
  if (NETWORK_ONLY.some((p) => url.pathname.startsWith(p))) return;

  // Pages: try the network (to pick up new versions), fall back to the saved app.
  if (req.mode === "navigate") {
    event.respondWith(
      fetch(req)
        .then((res) => {
          if (res.ok) {
            const copy = res.clone();
            caches.open(CACHE).then((c) => c.put("/", copy));
          }
          return res;
        })
        .catch(() => caches.match("/", { ignoreVary: true })),
    );
    return;
  }

  // Built files have a hash in their name, so a saved copy never goes stale.
  if (url.pathname.startsWith("/assets/")) {
    event.respondWith(
      caches.match(req, { ignoreVary: true }).then(
        (hit) =>
          hit ||
          fetch(req).then((res) => {
            if (res.ok) {
              const copy = res.clone();
              caches.open(CACHE).then((c) => c.put(req, copy));
            }
            return res;
          }),
      ),
    );
    return;
  }

  // Icons, manifest: use the saved copy, refresh it in the background.
  event.respondWith(
    caches.match(req, { ignoreVary: true }).then((hit) => {
      const fresh = fetch(req)
        .then((res) => {
          if (res.ok) {
            const copy = res.clone();
            caches.open(CACHE).then((c) => c.put(req, copy));
          }
          return res;
        })
        .catch(() => hit);
      return hit || fresh;
    }),
  );
});
