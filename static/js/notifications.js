/* Notification bell: polls the summary endpoint, shows offline state, optional browser notifications. */
document.addEventListener('alpine:init', () => {
  Alpine.data('notifBell', (cfg) => ({
    open: false, unread: cfg.unread || 0, alerts: 0, items: [], loading: false, failed: false,
    offline: !navigator.onLine, seen: new Set(), first: true, browserEnabled: false, timer: null,
    permission: ('Notification' in window) ? Notification.permission : 'unsupported',
    init() {
      this.refresh();
      this.timer = setInterval(() => { if (!document.hidden) this.refresh(); }, cfg.interval || 60000);
      document.addEventListener('visibilitychange', () => { if (!document.hidden) this.refresh(); });
      window.addEventListener('online', () => { this.offline = false; this.refresh(); });
      window.addEventListener('offline', () => { this.offline = true; });
    },
    async refresh() {
      if (!navigator.onLine) { this.offline = true; return; }
      this.loading = true;
      try {
        const r = await fetch(cfg.summaryUrl, { headers: { 'X-Requested-With': 'XMLHttpRequest' }, credentials: 'same-origin' });
        if (!r.ok) throw new Error(r.status);
        const d = await r.json();
        this.unread = d.unread; this.alerts = d.alerts; this.items = d.items; this.browserEnabled = d.browser_enabled;
        this.failed = false; this.offline = false;
        this.announceNew(d.items);
      } catch (e) { this.failed = true; } finally { this.loading = false; }
    },
    announceNew(items) {
      const fresh = items.filter(i => !i.read && !this.seen.has(i.id));
      items.forEach(i => this.seen.add(i.id));
      if (this.first) { this.first = false; return; }          // never replay existing items on page load
      if (this.browserEnabled && this.permission === 'granted' && document.hidden) {
        fresh.slice(0, 3).forEach(i => new Notification(i.title, { body: i.body, tag: i.id }));  // text is non-clinical by design
      }
    },
    async enableBrowser() {
      if (!('Notification' in window)) return;
      this.permission = await Notification.requestPermission();
      // Permission is the browser's gate; the user's own opt-in is the 'browser' column on the preferences page.
      if (this.permission === 'granted') window.location = cfg.preferencesUrl;
    },
    async post(url) {
      const f = new FormData(); f.append('csrfmiddlewaretoken', cfg.csrf);
      await fetch(url, { method: 'POST', body: f, headers: { 'X-Requested-With': 'XMLHttpRequest' }, credentials: 'same-origin' });
      await this.refresh();
    },
    markAll() { return this.post(cfg.markAllUrl); },
    ago(iso) {
      const s = Math.max(0, (Date.now() - new Date(iso)) / 1000);
      const rtf = new Intl.RelativeTimeFormat(document.documentElement.lang || 'en', { numeric: 'auto' });
      if (s < 3600) return rtf.format(-Math.round(s / 60), 'minute');
      if (s < 86400) return rtf.format(-Math.round(s / 3600), 'hour');
      return rtf.format(-Math.round(s / 86400), 'day');
    },
    dot(level) { return { success: 'bg-green-500', warning: 'bg-amber-500', danger: 'bg-red-500' }[level] || 'bg-sky-500'; },
  }));
});
