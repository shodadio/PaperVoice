'use strict';

const $id = (id) => document.getElementById(id);

const state = {
  engines: [],
  defaultEngine: '',
  book: null,
  timer: null,
  savePending: null,
  cancelling: false,
};

/* ---------- helpers ---------- */

function showError(message) {
  const box = $id('err');
  box.textContent = message || '';
  box.hidden = !message;
}

function toast(message) {
  const node = $id('toast');
  node.textContent = message;
  node.hidden = false;
  clearTimeout(toast.handle);
  toast.handle = setTimeout(() => { node.hidden = true; }, 4200);
}

function lockedOut() {
  document.body.innerHTML =
    '<div class="locked"><h1>Open the link from the Mac</h1>' +
    '<p>The URL printed in the terminal includes the access token. ' +
    'Open it once and this device is remembered.</p></div>';
}

async function api(path, options) {
  const settings = Object.assign({ credentials: 'same-origin' }, options || {});
  if (settings.body && typeof settings.body !== 'string') {
    settings.body = JSON.stringify(settings.body);
    settings.headers = Object.assign({ 'Content-Type': 'application/json' }, settings.headers || {});
  }
  const response = await fetch(path, settings);
  if (response.status === 401) { lockedOut(); throw new Error('locked'); }
  const raw = await response.text();
  let data = null;
  if (raw) { try { data = JSON.parse(raw); } catch (error) { data = null; } }
  if (!response.ok) {
    let detail = (data && data.detail) || raw || response.statusText;
    if (Array.isArray(detail)) detail = detail.map((item) => item.msg || JSON.stringify(item)).join('; ');
    throw new Error(String(detail));
  }
  return data;
}

function minutes(seconds) {
  if (!seconds) return 'a moment';
  if (seconds < 60) return 'under a minute';
  const mins = Math.round(seconds / 60);
  if (mins < 60) return `about ${mins} min`;
  const hours = Math.floor(mins / 60);
  return `about ${hours} h ${mins % 60} min`;
}

function statusLabel(status) {
  return { ready: 'ready', processing: 'processing', done: 'audio ready', error: 'failed' }[status] || status;
}

/* ---------- library ---------- */

async function refreshLibrary() {
  const data = await api('/api/books');
  renderLibrary(data.books || []);
}

function renderLibrary(books) {
  const list = $id('books');
  list.textContent = '';
  $id('empty').hidden = books.length > 0;

  books.forEach((book) => {
    const row = document.createElement('li');
    row.className = 'book';

    const main = document.createElement('button');
    main.type = 'button';
    main.className = 'book-main';
    main.addEventListener('click', () => openBook(book.id));

    const title = document.createElement('strong');
    title.textContent = book.title;
    const meta = document.createElement('span');
    meta.className = 'meta';
    meta.textContent = `${book.includedCount}/${book.chapters.length} chapters · ${book.minutesEstimate} min · ${statusLabel(book.status)}`;

    main.append(title, meta);

    const remove = document.createElement('button');
    remove.type = 'button';
    remove.className = 'book-del';
    remove.textContent = 'Remove';
    remove.addEventListener('click', async (event) => {
      event.stopPropagation();
      if (!confirm(`Remove "${book.title}" and its audio?`)) return;
      try {
        await api(`/api/books/${book.id}`, { method: 'DELETE' });
        toast('Removed');
        if (state.book && state.book.id === book.id) showLibrary();
        await refreshLibrary();
      } catch (error) {
        toast(error.message);
      }
    });

    row.append(main, remove);
    list.append(row);
  });
}

function showLibrary() {
  state.book = null;
  stopPolling();
  $id('book').hidden = true;
  $id('library').hidden = false;
  refreshLibrary().catch((error) => { if (error.message !== 'locked') toast(error.message); });
}

/* ---------- book view ---------- */

async function openBook(id) {
  showError('');
  try {
    state.book = await api(`/api/books/${id}`);
    $id('library').hidden = true;
    $id('book').hidden = false;
    renderBook();
    window.scrollTo({ top: 0, behavior: 'instant' in window ? 'instant' : 'auto' });
    if (state.book.status === 'processing') startPolling();
  } catch (error) {
    if (error.message !== 'locked') toast(error.message);
  }
}

function renderBook() {
  const book = state.book;
  if (!book) return;

  $id('bookTitle').textContent = book.title;
  $id('bookMeta').textContent = [
    `${book.chapters.length} chapters`,
    `${book.minutesEstimate} min estimated`,
    book.sourceName,
  ].filter(Boolean).join(' · ');

  renderChapters(book);
  renderEngines(book);
  renderProgress(book);
  renderOutputs(book);
}

function renderChapters(book) {
  const list = $id('chapters');
  list.textContent = '';

  book.chapters.forEach((chapter) => {
    const row = document.createElement('li');
    row.className = 'ch' + (chapter.include ? '' : ' off') + (chapter.status === 'done' ? ' done' : '');

    const label = document.createElement('label');
    const box = document.createElement('input');
    box.type = 'checkbox';
    box.checked = chapter.include;
    box.dataset.idx = String(chapter.idx);
    box.addEventListener('change', () => {
      row.classList.toggle('off', !box.checked);
      scheduleSaveIncludes();
    });

    const title = document.createElement('span');
    title.className = 'ch-title';
    title.textContent = chapter.title;

    const meta = document.createElement('span');
    meta.className = 'meta';
    meta.textContent = `${chapter.minutes} min`;

    label.append(box, title, meta);
    row.append(label);
    list.append(row);
  });
}

function includedIndexes() {
  return Array.from($id('chapters').querySelectorAll('input:checked'))
    .map((box) => Number(box.dataset.idx));
}

function scheduleSaveIncludes() {
  clearTimeout(state.savePending);
  state.savePending = setTimeout(saveIncludes, 300);
}

async function saveIncludes() {
  if (!state.book) return;
  try {
    state.book = await api(`/api/books/${state.book.id}`, {
      method: 'PATCH',
      body: { include: includedIndexes() },
    });
    $id('bookMeta').textContent = [
      `${state.book.chapters.length} chapters`,
      `${state.book.minutesEstimate} min selected`,
      state.book.sourceName,
    ].filter(Boolean).join(' · ');
    renderOutputs(state.book);
  } catch (error) {
    if (error.message !== 'locked') showError(error.message);
  }
}

function renderEngines(book) {
  const engineSelect = $id('engine');
  if (!engineSelect.options.length) {
    state.engines.forEach((engine) => {
      const option = document.createElement('option');
      option.value = engine.id;
      option.textContent = engine.available ? engine.label : `${engine.label} (unavailable)`;
      option.disabled = !engine.available;
      engineSelect.append(option);
    });
  }

  const chosen = book.engine || state.defaultEngine || (state.engines[0] && state.engines[0].id) || '';
  if (chosen && engineSelect.value !== chosen) engineSelect.value = chosen;

  const engine = state.engines.find((item) => item.id === engineSelect.value) || {};
  const voiceSelect = $id('voice');
  voiceSelect.textContent = '';
  (engine.voices || []).forEach((voice) => {
    const option = document.createElement('option');
    option.value = voice.id;
    option.textContent = voice.label;
    voiceSelect.append(option);
  });
  const voice = book.voice || engine.default_voice || (engine.voices && engine.voices[0] && engine.voices[0].id) || '';
  if (voice) voiceSelect.value = voice;
  $id('voiceWrap').hidden = !(engine.voices || []).length;
  $id('engineHint').textContent = engine.hint || '';

  engineSelect.onchange = () => patchBook({ engine: engineSelect.value, voice: '' });
  voiceSelect.onchange = () => patchBook({ voice: voiceSelect.value });
}

async function patchBook(patch) {
  if (!state.book) return;
  try {
    state.book = await api(`/api/books/${state.book.id}`, { method: 'PATCH', body: patch });
    renderBook();
  } catch (error) {
    if (error.message !== 'locked') showError(error.message);
  }
}

function renderProgress(book) {
  const processing = book.status === 'processing';
  const button = $id('process');
  const cancelButton = $id('cancel');
  const hasAudio = (book.exports || []).length > 0;

  button.disabled = processing;
  button.textContent = processing ? 'Processing…' : (hasAudio ? 'Process again' : 'Process into audio');
  cancelButton.hidden = !processing;
  cancelButton.disabled = state.cancelling;
  cancelButton.textContent = state.cancelling ? 'Cancelling…' : 'Cancel';

  if (!processing) {
    $id('progWrap').hidden = true;
    if (book.status === 'error') showError(book.error || 'Processing failed.');
    else showError('');
    return;
  }

  const progress = book.progress || {};
  const total = progress.total || 1;
  const done = progress.done || 0;
  const percent = Math.min(100, Math.round((done / total) * 100));

  $id('progWrap').hidden = false;
  $id('progBar').style.width = `${percent}%`;

  const parts = [];
  if (progress.stage === 'bundling') parts.push('Building the file');
  else if (progress.chapters) parts.push(`Chapter ${progress.chapter || 1} of ${progress.chapters}`);
  parts.push(`${percent}%`);
  if (progress.eta) parts.push(`${minutes(progress.eta)} left`);
  $id('progText').textContent = parts.join(' · ');
}

function renderOutputs(book) {
  const formats = book.exports || [];
  const ready = formats.length > 0;
  $id('outStep').hidden = !ready;
  $id('outWrap').hidden = !ready;
  if (!ready) return;

  const savedName = localStorage.getItem(`name:${book.id}`) || book.title;
  const nameField = $id('name');
  if (document.activeElement !== nameField) nameField.value = savedName;

  let savedFormat = localStorage.getItem(`fmt:${book.id}`) || 'm4b';
  if (formats.indexOf(savedFormat) === -1) savedFormat = formats[0];
  const radio = document.querySelector(`input[name="fmt"][value="${savedFormat}"]`);
  if (radio) radio.checked = true;

  updateDownload();
}

function updateDownload() {
  const book = state.book;
  if (!book) return;
  const checked = document.querySelector('input[name="fmt"]:checked');
  const format = checked ? checked.value : 'm4b';
  const name = ($id('name').value || '').trim() || book.title;
  localStorage.setItem(`name:${book.id}`, name);
  localStorage.setItem(`fmt:${book.id}`, format);

  const link = $id('download');
  link.href = `/api/books/${book.id}/download?format=${encodeURIComponent(format)}&name=${encodeURIComponent(name)}`;
  link.textContent = `Download ${format.toUpperCase()}`;
}

/* ---------- processing ---------- */

async function startProcessing() {
  if (!state.book) return;
  showError('');
  state.cancelling = false;
  const button = $id('process');
  button.disabled = true;
  button.textContent = 'Starting…';
  try {
    state.book = await api(`/api/books/${state.book.id}/process`, { method: 'POST' });
    renderBook();
    startPolling();
  } catch (error) {
    button.disabled = false;
    if (error.message !== 'locked') showError(error.message);
    renderProgress(state.book);
  }
}

async function cancelProcessing() {
  if (!state.book || state.cancelling) return;
  state.cancelling = true;
  renderProgress(state.book);
  try {
    await api(`/api/books/${state.book.id}/cancel`, { method: 'POST' });
  } catch (error) {
    state.cancelling = false;
    renderProgress(state.book);
    if (error.message !== 'locked') showError(error.message);
  }
}

function startPolling() {
  if (state.timer) return;
  state.timer = setInterval(syncBook, 1200);
}

function stopPolling() {
  clearInterval(state.timer);
  state.timer = null;
}

async function syncBook() {
  if (!state.book) { stopPolling(); return; }
  const id = state.book.id;
  try {
    const fresh = await api(`/api/books/${id}`);
    if (!state.book || state.book.id !== id) return;
    const wasProcessing = state.book.status === 'processing';
    state.book = fresh;
    renderBook();
    if (fresh.status !== 'processing') {
      stopPolling();
      state.cancelling = false;
      if (wasProcessing && fresh.status === 'done') {
        toast('Audio ready');
        refreshLibrary().catch(() => {});
      } else if (wasProcessing && (fresh.progress || {}).stage === 'cancelled') {
        toast('Cancelled — the chapters already finished are kept');
        refreshLibrary().catch(() => {});
      }
    }
  } catch (error) {
    stopPolling();
    if (error.message !== 'locked') showError(error.message);
  }
}

/* ---------- upload ---------- */

function uploadFile(file) {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    form.append('file', file);
    const request = new XMLHttpRequest();
    request.open('POST', '/api/books');
    request.withCredentials = true;
    request.upload.addEventListener('progress', (event) => {
      if (event.lengthComputable) {
        toast(`Uploading ${file.name} · ${Math.round((event.loaded / event.total) * 100)}%`);
      }
    });
    request.addEventListener('load', () => {
      if (request.status >= 200 && request.status < 300) {
        try { resolve(JSON.parse(request.responseText)); } catch (error) { reject(new Error('Unexpected reply from the server.')); }
        return;
      }
      let message = `Upload failed (${request.status})`;
      try {
        const parsed = JSON.parse(request.responseText);
        if (parsed && parsed.detail) message = String(parsed.detail);
      } catch (error) { /* keep the status message */ }
      reject(new Error(message));
    });
    request.addEventListener('error', () => reject(new Error('Upload failed — is the Mac still awake?')));
    request.send(form);
  });
}

async function handleFiles(fileList) {
  const files = Array.from(fileList || []);
  if (!files.length) return;
  let last = null;
  for (const file of files) {
    try {
      toast(`Reading ${file.name}…`);
      last = await uploadFile(file);
      toast(`${last.title} · ${last.chapters.length} chapters`);
    } catch (error) {
      toast(error.message);
    }
  }
  await refreshLibrary().catch(() => {});
  if (last) await openBook(last.id);
}

/* ---------- wiring ---------- */

function boot() {
  $id('file').addEventListener('change', async (event) => {
    await handleFiles(event.target.files);
    event.target.value = '';
  });

  const drop = $id('drop');
  ['dragenter', 'dragover'].forEach((name) => {
    drop.addEventListener(name, (event) => { event.preventDefault(); drop.classList.add('hot'); });
  });
  ['dragleave', 'drop'].forEach((name) => {
    drop.addEventListener(name, (event) => { event.preventDefault(); drop.classList.remove('hot'); });
  });
  drop.addEventListener('drop', (event) => {
    if (event.dataTransfer && event.dataTransfer.files) handleFiles(event.dataTransfer.files);
  });

  $id('back').addEventListener('click', showLibrary);

  $id('allOn').addEventListener('click', () => {
    $id('chapters').querySelectorAll('input').forEach((box) => { box.checked = true; box.closest('.ch').classList.remove('off'); });
    scheduleSaveIncludes();
  });
  $id('allOff').addEventListener('click', () => {
    $id('chapters').querySelectorAll('input').forEach((box) => { box.checked = false; box.closest('.ch').classList.add('off'); });
    scheduleSaveIncludes();
  });

  $id('process').addEventListener('click', startProcessing);
  $id('cancel').addEventListener('click', cancelProcessing);
  $id('name').addEventListener('input', updateDownload);
  $id('formats').addEventListener('change', updateDownload);

  document.addEventListener('visibilitychange', () => {
    if (!document.hidden && state.book) syncBook();
  });

  api('/api/engines')
    .then((data) => {
      state.engines = data.engines || [];
      state.defaultEngine = data.default || '';
      return refreshLibrary();
    })
    .catch((error) => {
      if (error.message !== 'locked') toast(error.message);
    });

  if ('serviceWorker' in navigator && window.isSecureContext) {
    navigator.serviceWorker.register('/sw.js').catch(() => {});
  }

  const host = location.hostname;
  if (host && host !== 'localhost' && host !== '127.0.0.1') {
    $id('net').hidden = false;
  }
}

document.addEventListener('DOMContentLoaded', boot);
