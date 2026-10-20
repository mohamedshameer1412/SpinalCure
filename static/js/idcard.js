/* ID card behaviour: responsive scaling, flip, PNG/PDF export, sharing. Vanilla JS; libraries are vendored. */
(function () {
  'use strict';
  var FACE_W = 560, FACE_H = 900, EXPORT_SCALE = 3;

  function toast(msg) {
    var t = document.createElement('div');
    t.className = 'idc-toast'; t.setAttribute('role', 'status'); t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(function () { t.remove(); }, 3500);
  }

  function initStage(stage) {
    var scaler = stage.querySelector('.idc-scale'), flip = stage.querySelector('.idc-flip');
    if (!scaler || !flip) return;
    function fit() {
      var k = Math.min(1, stage.clientWidth / FACE_W) || 1;
      scaler.style.transform = 'scale(' + k + ')';
      stage.style.height = Math.round(FACE_H * k) + 'px';
    }
    if ('ResizeObserver' in window) { new ResizeObserver(fit).observe(stage); } else { window.addEventListener('resize', fit); }
    fit();
    function setFlipped(on) {
      flip.classList.toggle('is-flipped', on);
      flip.setAttribute('aria-pressed', on ? 'true' : 'false');
      flip.setAttribute('aria-label', on ? flip.dataset.labelBack : flip.dataset.labelFront);
    }
    flip.addEventListener('click', function () { setFlipped(!flip.classList.contains('is-flipped')); });
    flip.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setFlipped(!flip.classList.contains('is-flipped')); }
    });
    stage._setFlipped = setFlipped;
    stage._toggle = function () { setFlipped(!flip.classList.contains('is-flipped')); };
  }

  function waitForFonts() {
    return (document.fonts && document.fonts.ready) ? document.fonts.ready : Promise.resolve();
  }

  function renderFace(el) {
    return waitForFonts().then(function () {
      return window.html2canvas(el, { scale: EXPORT_SCALE, backgroundColor: '#ffffff', useCORS: true, logging: false,
                                      width: FACE_W, height: FACE_H, windowWidth: FACE_W + 200, scrollX: 0, scrollY: 0 });
    });
  }

  function releaseCanvas(c) { c.width = 0; c.height = 0; }     // free the bitmap right away

  function download(blob, filename) {
    var url = URL.createObjectURL(blob), a = document.createElement('a');
    a.href = url; a.download = filename; document.body.appendChild(a); a.click(); a.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 2000);
  }

  function canvasToBlob(canvas) {
    return new Promise(function (resolve, reject) {
      canvas.toBlob(function (b) { b ? resolve(b) : reject(new Error('Could not encode the image')); }, 'image/png');
    });
  }

  function exportPng(root, side, filename) {
    var el = root.querySelector('[data-idc-export="' + side + '"]');
    return renderFace(el).then(function (canvas) {
      return canvasToBlob(canvas).then(function (blob) {
        var info = { width: canvas.width, height: canvas.height };
        releaseCanvas(canvas); download(blob, filename); return info;
      });
    });
  }

  function exportPdf(root, filename) {
    var jsPDF = window.jspdf && window.jspdf.jsPDF;
    var front = root.querySelector('[data-idc-export="front"]'), back = root.querySelector('[data-idc-export="back"]');
    return renderFace(front).then(function (fc) {
      return renderFace(back).then(function (bc) {
        var pdf = new jsPDF({ orientation: 'portrait', unit: 'px', format: [FACE_W, FACE_H], compress: true, hotfixes: ['px_scaling'] });
        pdf.addImage(fc.toDataURL('image/png'), 'PNG', 0, 0, FACE_W, FACE_H);
        pdf.addPage([FACE_W, FACE_H], 'portrait');
        pdf.addImage(bc.toDataURL('image/png'), 'PNG', 0, 0, FACE_W, FACE_H);
        releaseCanvas(fc); releaseCanvas(bc);
        var blob = pdf.output('blob'); download(blob, filename); return { pages: pdf.getNumberOfPages() };
      });
    });
  }

  function shareMessage(root) {
    var d = root.dataset;
    return d.shareText + ' ' + d.verifyUrl;
  }

  function nativeShare(root) {
    var d = root.dataset, data = { title: d.shareTitle, text: d.shareText, url: d.shareUrl || d.verifyUrl };
    if (navigator.share && (!navigator.canShare || navigator.canShare(data))) {
      return navigator.share(data).catch(function (e) { if (e && e.name !== 'AbortError') throw e; });
    }
    var link = data.url;                                                             // safe fallback: copy the link
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(link).then(function () { toast(root.dataset.msgCopied); });
    }
    window.prompt(root.dataset.msgCopyPrompt, link);                                 // last resort
    return Promise.resolve();
  }

  function whatsapp(root) {   // opens a prefilled chat for the user to review and send; nothing is sent automatically
    window.open('https://wa.me/?text=' + encodeURIComponent(shareMessage(root)), '_blank', 'noopener');
  }

  function busy(btn, on) { btn.disabled = on; btn.setAttribute('aria-busy', on ? 'true' : 'false'); }

  function wire(root) {
    root.querySelectorAll('.idc-stage').forEach(initStage);
    root.addEventListener('click', function (e) {
      var flipBtn = e.target.closest('[data-idc-flip]');          // the toolbar sits outside the stage, so wire it from the root
      if (flipBtn) { var st = root.querySelector('.idc-stage'); if (st && st._toggle) st._toggle(); return; }
      var btn = e.target.closest('[data-idc-action]');
      if (!btn) return;
      var action = btn.dataset.idcAction, name = root.dataset.filename || 'id-card';
      var run;
      if (action === 'png-front') run = function () { return exportPng(root, 'front', name + '-front.png'); };
      else if (action === 'png-back') run = function () { return exportPng(root, 'back', name + '-back.png'); };
      else if (action === 'pdf') run = function () { return exportPdf(root, name + '.pdf'); };
      else if (action === 'share') run = function () { return nativeShare(root); };
      else if (action === 'whatsapp') { whatsapp(root); return; }
      else if (action === 'print') { window.print(); return; }
      else return;
      busy(btn, true);
      Promise.resolve().then(run).then(function () { if (action !== 'share') toast(root.dataset.msgDone); })
        .catch(function (err) { console.error(err); toast(root.dataset.msgFailed); })
        .then(function () { busy(btn, false); });
    });
    root.dataset.idcReady = '1';
  }

  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('[data-idc-root]').forEach(wire);
  });
  window.IDCard = { exportPng: exportPng, exportPdf: exportPdf };
})();
