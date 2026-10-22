/* Spinal Cure UI kit behaviour. Loaded (deferred) before Alpine so the stores register on `alpine:init`.
   - Alpine.store('theme'):  light | dark | system, persisted in localStorage
   - Alpine.store('toast'):  Alpine.store('toast').push('Saved', 'success')
   - File dropzone:          every <input type="file"> becomes a drag-and-drop area (opt out with data-plain)
   Markup for the components lives in templates/ui/. */
(function () {
  'use strict';

  // Phone fields show a fixed +91 prefix; a number typed with its own +code is kept as typed.
  window.withCountryCode = function (v) {
    v = (v || '').trim();
    if (!v || v.charAt(0) === '+') return v;
    return '+91 ' + v.replace(/^0+/, '');
  };

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

  // Dropdowns: every <select> becomes a styled Tom Select (no browser-default popups anywhere).
  // Opt out only with data-native (e.g. a select that a script already replaces with its own UI).
  // Short lists get no search box; long ones are searchable. Selects added later (Alpine x-if / x-for,
  // htmx swaps) are picked up by the observer below.
  function enhanceSelect(el) {
    if (el.tomselect || el.hasAttribute('data-native') || el.closest('.flatpickr-calendar') || typeof window.TomSelect === 'undefined') return;
    var root = document.documentElement, staff = !root.hasAttribute('data-fixed-theme');
    var empty = el.querySelector('option[value=""]');
    var count = el.options.length;
    var ts = new TomSelect(el, {
      create: el.hasAttribute('data-create'),            // suggestions plus free typing (e.g. "Checked by")
      createOnBlur: el.hasAttribute('data-create'),
      addPrecedence: el.hasAttribute('data-create'),     // the typed name is offered first, so Enter keeps what was typed
      allowEmptyOption: !!empty,
      maxOptions: 500,
      plugins: el.hasAttribute('data-create') ? ['dropdown_input'] : [],
      controlInput: el.hasAttribute('data-create') ? '<input type="text" autocomplete="off" size="1" />' : (count > 8 ? undefined : null),
      placeholder: el.getAttribute('data-placeholder') || (empty && empty.textContent.trim()) || root.dataset.tsPlaceholder || '',
      // staff lists are alphabetical unless marked; public lists keep the order they were written in
      sortField: staff && !el.classList.contains('no-sort') && el.name !== 'category' && !el.hasAttribute('data-keep-order')
        ? { field: 'text', direction: 'asc' } : null,
      render: { no_results: function () { return '<div class="no-results">' + (root.dataset.tsNoResults || 'No results') + '</div>'; } },
      onInitialize: function () { this.wrapper.classList.toggle('ts-compact', count <= 8 && !el.hasAttribute('data-create')); },
    });
    // keep onchange="this.form.submit()" and Alpine x-model working
    ts.on('change', function () { el.dispatchEvent(new Event('change', { bubbles: true })); el.dispatchEvent(new Event('input', { bubbles: true })); });
  }

  // Date / time fields: flatpickr calendar instead of the browser's picker (also on phones). The original input keeps
  // its name and ISO value (Y-m-d / H:i), so forms and servers are unchanged. Month and day names come from Intl
  // in the page language, so Tamil, Telugu, Malayalam and Kannada get native calendars too. Opt out: data-native.
  var fpLocale = null;
  function pickerLocale() {
    if (fpLocale) return fpLocale;
    var lang = document.documentElement.lang || 'en';
    var fmt = function (opts, d) { return new Intl.DateTimeFormat(lang, opts).format(d); };
    var day = function (i) { return new Date(Date.UTC(2023, 0, 1 + i)); };            // 1 Jan 2023 was a Sunday
    var month = function (i) { return new Date(Date.UTC(2023, i, 15)); };
    var range = function (n, f) { var a = []; for (var i = 0; i < n; i++) a.push(f(i)); return a; };
    try {
      fpLocale = {
        // Indic short weekday names are long; the narrow form keeps seven columns readable
        weekdays: { shorthand: range(7, function (i) { return fmt({ weekday: lang.indexOf('en') === 0 ? 'short' : 'narrow', timeZone: 'UTC' }, day(i)); }),
                    longhand: range(7, function (i) { return fmt({ weekday: 'long', timeZone: 'UTC' }, day(i)); }) },
        months: { shorthand: range(12, function (i) { return fmt({ month: 'short', timeZone: 'UTC' }, month(i)); }),
                  longhand: range(12, function (i) { return fmt({ month: 'long', timeZone: 'UTC' }, month(i)); }) },
        firstDayOfWeek: 1, rangeSeparator: ' – ',
      };
    } catch (e) { fpLocale = {}; }
    return fpLocale;
  }
  function enhanceDate(el) {
    if (el._flatpickr || el.hasAttribute('data-native') || typeof window.flatpickr === 'undefined') return;
    var type = el.getAttribute('type');
    var time = type === 'time', both = type === 'datetime-local';
    var fp = flatpickr(el, {
      locale: pickerLocale(), disableMobile: true, allowInput: true, monthSelectorType: 'static',
      altInput: true, altInputClass: (el.className + ' flatpickr-alt').trim(),
      dateFormat: time ? 'H:i' : (both ? 'Y-m-d\\TH:i' : 'Y-m-d'),
      altFormat: time ? 'h:i K' : (both ? 'j M Y, h:i K' : 'j M Y'),
      enableTime: time || both, noCalendar: time, minuteIncrement: 5,
      minDate: el.min || null, maxDate: el.max || null,     // flatpickr itself fires change + input on the original
    });
    if (fp.altInput) {
      if (el.id) { fp.altInput.id = el.id; el.removeAttribute('id'); }   // labels keep pointing at what people type in
      if (el.required) { fp.altInput.required = true; el.required = false; }
      if (el.placeholder) fp.altInput.placeholder = el.placeholder;
      else fp.altInput.placeholder = time ? '--:--' : '';
    }
  }

  function enhanceAll(root) {
    root = root || document;
    root.querySelectorAll('input[type=file]').forEach(enhanceFile);
    root.querySelectorAll('select').forEach(enhanceSelect);
    root.querySelectorAll('input[type=date], input[type=time], input[type=datetime-local]').forEach(enhanceDate);
  }
  document.addEventListener('DOMContentLoaded', function () {
    enhanceAll();
    new MutationObserver(function (records) {
      records.forEach(function (r) {
        r.addedNodes.forEach(function (n) {
          if (n.nodeType !== 1 || n.closest('.ts-wrapper, .ts-dropdown')) return;
          if (n.matches('select')) enhanceSelect(n); else if (n.querySelector('select, input[type=file], input[type=date], input[type=time], input[type=datetime-local]')) enhanceAll(n);
        });
      });
    }).observe(document.body, { childList: true, subtree: true });
  });
  document.addEventListener('htmx:afterSwap', function (e) { enhanceAll(e.target); });
})();
