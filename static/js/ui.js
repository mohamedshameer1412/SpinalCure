/* Spinal Cure UI kit behaviour. Loaded (deferred) before Alpine so the stores register on `alpine:init`.
   - Alpine.store('theme'):  light | dark | system, persisted in localStorage
   - Alpine.store('toast'):  Alpine.store('toast').push('Saved', 'success')
   - File dropzone:          every <input type="file"> becomes a drag-and-drop area (opt out with data-plain)
   Markup for the components lives in templates/ui/. */
(function () {
  'use strict';

  var media = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;
  function applyTheme(mode) {
    if (document.documentElement.hasAttribute('data-fixed-theme')) return;   // public site is light-only
    var dark = mode === 'dark' || (mode === 'system' && media && media.matches);
    document.documentElement.classList.toggle('dark', dark);
  }

  document.addEventListener('alpine:init', function () {
    var saved = 'system';
    try { saved = localStorage.getItem('theme') || 'system'; } catch (e) {}
    Alpine.store('theme', {
      mode: saved,
      set: function (m) {
        this.mode = m;
        try { localStorage.setItem('theme', m); } catch (e) {}
        applyTheme(m);
      },
      get isDark() { return document.documentElement.classList.contains('dark'); },
    });
    if (media && media.addEventListener) media.addEventListener('change', function () { applyTheme(Alpine.store('theme').mode); });

    var seq = 0;
    Alpine.store('toast', {
      items: [],
      push: function (message, type, ms) {
        var id = ++seq, self = this;
        this.items.push({ id: id, message: message, type: type || 'info' });
        setTimeout(function () { self.dismiss(id); }, ms || 5000);
      },
      dismiss: function (id) { this.items = this.items.filter(function (t) { return t.id !== id; }); },
    });
  });

  // ---- file dropzone ------------------------------------------------------------------------
  function humanSize(n) { return n > 1048576 ? (n / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(n / 1024)) + ' KB'; }

  function enhanceFile(input) {
    if (input.dataset.plain !== undefined || input.dataset.dz || input.closest('.dropzone')) return;
    input.dataset.dz = '1';
    var zone = document.createElement('div');
    zone.className = 'dropzone';
    var accept = input.getAttribute('accept');
    function el(tag, cls, text) {
      var n = document.createElement(tag);
      if (cls) n.className = cls;
      if (text) n.textContent = text;
      return n;
    }
    var icon = el('i', 'bi bi-cloud-arrow-up dropzone-icon');
    icon.setAttribute('aria-hidden', 'true');
    var text = el('div', 'dropzone-text');
    text.appendChild(el('b', '', input.multiple ? 'Choose files' : 'Choose a file'));
    text.appendChild(document.createTextNode(' or drag it here'));
    zone.appendChild(icon);
    zone.appendChild(text);
    if (accept) zone.appendChild(el('div', 'dropzone-hint', accept.replace(/,/g, ', ')));
    zone.appendChild(el('div', 'dropzone-files'));
    input.parentNode.insertBefore(zone, input);
    zone.insertBefore(input, zone.firstChild);
    var list = zone.querySelector('.dropzone-files');

    function render() {
      while (list.firstChild) list.removeChild(list.firstChild);
      Array.prototype.forEach.call(input.files || [], function (f) {
        var chip = document.createElement('span');
        chip.className = 'dropzone-file';
        if (/^image\//.test(f.type)) {
          var img = document.createElement('img');
          img.alt = '';
          img.src = URL.createObjectURL(f);
          chip.appendChild(img);
        } else {
          var ico = document.createElement('i');
          ico.className = 'bi bi-file-earmark';
          ico.setAttribute('aria-hidden', 'true');
          chip.appendChild(ico);
        }
        var name = document.createElement('span');
        name.className = 'truncate';
        name.textContent = f.name + ' · ' + humanSize(f.size);
        chip.appendChild(name);
        list.appendChild(chip);
      });
    }
    input.addEventListener('change', render);
    ['dragenter', 'dragover'].forEach(function (ev) {
      zone.addEventListener(ev, function () { zone.classList.add('is-drag'); });
    });
    ['dragleave', 'drop'].forEach(function (ev) {
      zone.addEventListener(ev, function () { zone.classList.remove('is-drag'); });
    });
  }

  function enhanceAll(root) {
    (root || document).querySelectorAll('input[type=file]').forEach(enhanceFile);
  }
  document.addEventListener('DOMContentLoaded', function () { enhanceAll(); });
  document.addEventListener('htmx:afterSwap', function (e) { enhanceAll(e.target); });
})();
