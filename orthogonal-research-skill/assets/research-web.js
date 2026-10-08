/* All enhancements are local and deterministic. No fetch, dependencies, eval or analytics. */
(() => {
  'use strict';
  const $ = (s, root = document) => root.querySelector(s);
  const $$ = (s, root = document) => Array.from(root.querySelectorAll(s));
  const data = JSON.parse($('#research-web-data').textContent);
  const components = new Map(data.components.map(c => [c.id, c]));
  document.documentElement.classList.add('rw-js-ready');
  const narrowScreen = matchMedia('(max-width:760px)');
  const setTocDefault = () => { $('#reader-toc').open = !narrowScreen.matches; };
  setTocDefault();
  if (narrowScreen.addEventListener) narrowScreen.addEventListener('change', setTocDefault);
  else narrowScreen.addListener(setTocDefault);
  const announce = (element, text) => { if (element) element.textContent = text; };
  const normalize = text => String(text).normalize('NFKC').toLocaleLowerCase();
  const number = value => String(value);
  // Error-free partial sums mirror Python's math.fsum, including cancellation.
  function fsum(values) {
    const partials = [];
    for (let x of values) {
      let index = 0;
      for (let y of partials) {
        if (Math.abs(x) < Math.abs(y)) [x, y] = [y, x];
        const high = x + y, low = y - (high - x);
        if (low) partials[index++] = low;
        x = high;
      }
      partials.length = index;
      if (x) partials.push(x);
    }
    let n = partials.length, high = 0, low = 0;
    if (n) {
      high = partials[--n];
      while (n) { const x = high, y = partials[--n]; high = x + y; low = y - (high - x); if (low) break; }
      if (n && ((low < 0 && partials[n - 1] < 0) || (low > 0 && partials[n - 1] > 0))) { const y = low * 2, x = high + y; if (y === x - high) high = x; }
    }
    return high;
  }
  const anchors = new Map(data.headings.map(h => [h.id, h.title]));
  Object.values(data.sources).forEach(s => anchors.set('source-' + s.id, s.title));
  $$('.rw-prose h1[id],.rw-prose h2[id],.rw-prose h3[id],.rw-prose h4[id]').filter(h => !h.closest('.rw-widget')).forEach(h => {
    const b = document.createElement('button');
    b.type = 'button'; b.className = 'rw-save rw-js'; b.dataset.bookmark = h.id;
    b.setAttribute('aria-label', '收藏章节：' + anchors.get(h.id)); b.setAttribute('aria-pressed', 'false');
    b.textContent = '收藏'; h.append(b);
  });

  // Each study has its own notebook. Corrupt stored data is retained for recovery.
  const storageKey = 'orthogonal:reader:v1:' + encodeURIComponent(data.study.id) + ':' + encodeURIComponent(data.study.as_of);
  const blank = () => ({version: 1, study: data.study.id, as_of: data.study.as_of, notes: '', bookmarks: []});
  let record = blank(), recovery = null, storageOK = true;
  function validateRecord(value) {
    if (!value || typeof value !== 'object' || Array.isArray(value) || value.version !== 1 || value.study !== data.study.id || value.as_of !== data.study.as_of || typeof value.notes !== 'string' || !Array.isArray(value.bookmarks)) throw Error('这份记录不属于当前报告及研究截面，或文件格式不受支持。');
    if (value.notes.length > 20000 || value.bookmarks.length > 500) throw Error('记录过大；当前笔记保持不变。');
    if (value.bookmarks.some(id => typeof id !== 'string' || !anchors.has(id))) throw Error('记录含有当前报告不存在的收藏位置；当前笔记保持不变。');
    return {version: 1, study: data.study.id, as_of: data.study.as_of, notes: value.notes, bookmarks: [...new Set(value.bookmarks)]};
  }
  try { const raw = localStorage.getItem(storageKey); if (raw !== null) { try { record = validateRecord(JSON.parse(raw)); } catch (_) { recovery = raw; } } } catch (_) { storageOK = false; }
  function status() {
    announce($('#rw-storage-status'), recovery !== null ? '检测到旧记录格式异常，原始内容仍保留。当前编辑不会覆盖旧记录，请导出保存。' : storageOK ? '已自动保存在当前浏览器；笔记 ' + record.notes.length + ' / 20000 字符。' : '浏览器无法持久保存，当前记录仅在本页暂存，请导出文件保留。');
    $('#rw-recover').hidden = recovery === null;
  }
  function persist() {
    if (recovery === null) { try { localStorage.setItem(storageKey, JSON.stringify(record)); storageOK = true; } catch (_) { storageOK = false; } }
    status();
  }
  function syncBookmarks() {
    $$('[data-bookmark]').forEach(b => { const saved = record.bookmarks.includes(b.dataset.bookmark); b.setAttribute('aria-pressed', String(saved)); b.textContent = saved ? '已收藏' : (b.dataset.bookmark.startsWith('source-') ? '收藏来源' : '收藏'); });
    $('#rw-bookmark-count').textContent = String(record.bookmarks.length);
    const list = $('#rw-bookmarks'); list.replaceChildren();
    if (!record.bookmarks.length) { const li = document.createElement('li'); li.textContent = '尚未收藏。可使用章节、组件和来源旁的收藏按钮。'; list.append(li); }
    record.bookmarks.forEach(id => {
      const li = document.createElement('li'), a = document.createElement('a'), b = document.createElement('button');
      a.href = '#' + id; a.textContent = anchors.get(id); b.type = 'button'; b.dataset.removeBookmark = id; b.textContent = '移除'; b.setAttribute('aria-label', '移除收藏：' + anchors.get(id));
      li.append(a, b); list.append(li);
    });
  }
  $('#rw-notes').value = record.notes; status(); syncBookmarks();
  $('#rw-notes').addEventListener('input', event => { record.notes = event.target.value.slice(0, 20000); persist(); });
  document.addEventListener('click', event => {
    const save = event.target.closest('[data-bookmark]');
    if (save && anchors.has(save.dataset.bookmark)) {
      const id = save.dataset.bookmark;
      record.bookmarks = record.bookmarks.includes(id) ? record.bookmarks.filter(v => v !== id) : [...record.bookmarks, id];
      persist(); syncBookmarks();
    }
    const remove = event.target.closest('[data-remove-bookmark]');
    if (remove) { record.bookmarks = record.bookmarks.filter(id => id !== remove.dataset.removeBookmark); persist(); syncBookmarks(); }
  });
  function download(text, filename) {
    const url = URL.createObjectURL(new Blob([text], {type: 'application/json;charset=utf-8'}));
    const a = document.createElement('a'); a.href = url; a.download = filename; document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  const filename = data.study.id.replace(/[^a-z0-9_-]/gi, '_').slice(0, 90) || 'research';
  $('#rw-export').addEventListener('click', () => download(JSON.stringify({...record, title: data.study.title, exported_at: new Date().toISOString()}, null, 2), filename + '-notes.json'));
  $('#rw-recover').addEventListener('click', () => { if (recovery !== null) download(recovery, filename + '-recovery.json'); });
  $('#rw-import').addEventListener('change', async event => {
    const file = event.target.files[0]; if (!file) return;
    try {
      if (file.size > 300000) throw Error('文件超过 300 KB，当前记录保持不变。');
      const incoming = validateRecord(JSON.parse(await file.text()));
      // Merge instead of silently overwriting current user work.
      let notes = record.notes;
      if (incoming.notes && incoming.notes !== record.notes && !record.notes.includes(incoming.notes)) notes = notes ? notes + '\n\n——导入记录——\n' + incoming.notes : incoming.notes;
      if (notes.length > 20000) throw Error('合并后笔记超过 20000 字符，请先整理记录。当前记录保持不变。');
      record = {...record, notes, bookmarks: [...new Set([...record.bookmarks, ...incoming.bookmarks])]};
      $('#rw-notes').value = record.notes; persist(); syncBookmarks(); announce($('#rw-import-status'), '已合并导入笔记和收藏。');
    } catch (error) { announce($('#rw-import-status'), error instanceof SyntaxError ? '文件不是有效的 JSON；当前记录保持不变。' : error.message); }
    event.target.value = '';
  });

  // Build full-text search from readable content, without replacing report text.
  let searchIndex = [];
  $$('.rw-prose h1,.rw-prose h2,.rw-prose h3,.rw-prose h4,.rw-prose p,.rw-prose li,.rw-prose tr,.rw-widget h3,.rw-widget .rw-item,.rw-widget li,.rw-widget tr,.rw-widget .rw-glossary>div,.rw-widget .rw-node,.rw-widget .rw-limit,.rw-widget .rw-conclusion,.rw-sources>ol>li').forEach((element, i) => {
    const copy = element.cloneNode(true); $$('button,input,select,textarea', copy).forEach(n => n.remove());
    const text = copy.textContent.trim(); if (!text) return;
    if (!element.id) element.id = 'rw-search-block-' + i;
    const section = element.closest('.rw-widget,[data-source-record]');
    const title = section ? ($('h3', section)?.textContent || '来源') : (element.matches('h1,h2,h3,h4') ? text : (() => { let p = element; while (p) { if (p.matches('h1,h2,h3,h4')) return p.textContent.replace(/已收藏|收藏/g, '').trim(); p = p.previousElementSibling; } return '正文'; })());
    searchIndex.push({element, text, normalized: normalize(text), title});
  });
  function search() {
    const query = normalize($('#rw-search-input').value.trim()).slice(0, 160), list = $('#rw-search-results'); list.replaceChildren();
    if (!query) { announce($('#rw-search-status'), '输入关键词检索完整报告。'); return; }
    const hits = searchIndex.filter(item => item.normalized.includes(query));
    announce($('#rw-search-status'), '找到 ' + hits.length + ' 处匹配' + (hits.length > 80 ? '，先显示前 80 处。' : '。'));
    hits.slice(0, 80).forEach(hit => {
      const li = document.createElement('li'), a = document.createElement('a'), p = document.createElement('p');
      a.href = '#' + hit.element.id; a.textContent = hit.title.replace(/已收藏|收藏/g, '').trim().slice(0, 100);
      const pos = hit.normalized.indexOf(query), start = Math.max(0, pos - 45), end = Math.min(hit.text.length, pos + query.length + 90);
      p.textContent = (start ? '…' : '') + hit.text.slice(start, end) + (end < hit.text.length ? '…' : '');
      a.addEventListener('click', () => {
        const widget = hit.element.closest('.rw-widget');
        if (widget) {
          $('[data-select-all]', widget)?.click();
          $$('[data-filter],[data-category],[data-node]', widget).forEach(control => { control.value = ''; control.dispatchEvent(new Event(control.matches('[data-filter]') ? 'input' : 'change', {bubbles:true})); });
          $$('[data-series-toggle]', widget).forEach(control => { control.checked = true; control.dispatchEvent(new Event('change', {bubbles:true})); });
        }
        let current = hit.element;
        while (current && current !== document.body) { current.hidden = false; if (current.tagName === 'DETAILS') current.open = true; current = current.parentElement; }
      });
      li.append(a, p); list.append(li);
    });
  }
  let searchTimer; $('#rw-search-input').addEventListener('input', () => { clearTimeout(searchTimer); searchTimer = setTimeout(search, 120); });
  $('#rw-search-clear').addEventListener('click', () => { $('#rw-search-input').value = ''; search(); $('#rw-search-input').focus(); }); search();

  $$('.rw-widget').forEach(widget => {
    const component = components.get(widget.dataset.component);
    if (!component) return;
    $$('[data-select],[data-select-all]', widget).forEach(button => button.addEventListener('click', () => {
      $$('[data-select],[data-select-all]', widget).forEach(b => b.setAttribute('aria-pressed', String(b === button)));
      $$('[data-item]', widget).forEach(item => { item.hidden = !button.hasAttribute('data-select-all') && item.dataset.item !== button.dataset.select; });
    }));
    const category = $('[data-category]', widget);
    if (category) category.addEventListener('change', () => $$('[data-category-item]', widget).forEach(item => { item.hidden = Boolean(category.value) && item.dataset.categoryItem !== category.value; }));
    const filter = $('[data-filter]', widget);
    if (filter) filter.addEventListener('input', () => {
      const needle = normalize(filter.value.trim()); let count = 0;
      $$('[data-filter-item]', widget).forEach(item => { item.hidden = !normalize(item.textContent).includes(needle); if (!item.hidden) count++; });
      announce($('.rw-filter-status', widget), count ? '显示 ' + count + ' 项。' : '没有匹配项，清空筛选可恢复全部内容。');
    });
    const node = $('[data-node]', widget);
    if (node) node.addEventListener('change', () => {
      const connected = new Set([node.value]);
      $$('.rw-link', widget).forEach(link => { const yes = !node.value || link.dataset.from === node.value || link.dataset.to === node.value; link.classList.toggle('rw-dimmed', !yes); if (yes) { connected.add(link.dataset.from); connected.add(link.dataset.to); } });
      $$('[data-node-item]', widget).forEach(item => { item.classList.toggle('rw-selected', item.dataset.nodeItem === node.value); item.classList.toggle('rw-dimmed', Boolean(node.value) && !connected.has(item.dataset.nodeItem)); });
    });
    $$('[data-evidence]', widget).forEach(input => input.addEventListener('change', () => {
      input.closest('.rw-item').classList.toggle('rw-selected', input.checked);
      announce($('.rw-evidence-status', widget), '当前选择 ' + $$('[data-evidence]:checked', widget).length + ' 项材料；研究结论不随勾选改变。');
    }));
    $$('[data-series-toggle]', widget).forEach(input => input.addEventListener('change', () => {
      $$('[data-series],[data-series-col]', widget).filter(n => (n.dataset.series || n.dataset.seriesCol) === input.dataset.seriesToggle).forEach(n => { n.style.display = input.checked ? '' : 'none'; });
    }));
    if (component.kind === 'calculator') {
      const inputs = $$('[data-input]', widget); inputs.forEach(input => { input.disabled = false; });
      function calculate() {
        const values = {};
        for (const input of inputs) {
          if (input.value.trim() === '' || !input.validity.valid || !Number.isFinite(Number(input.value))) { announce($('.rw-calc-status', widget), '请按给定范围和步长输入有效数值；保留上次有效结果。'); return; }
          values[input.dataset.input] = Number(input.value);
        }
        const results = component.outputs.map(output => ({id: output.id, value: fsum([output.base, ...output.terms.map(term => values[term.input] * term.coefficient)])}));
        if (results.some(output => !Number.isFinite(output.value))) { announce($('.rw-calc-status', widget), '计算超出可表示范围；保留上次有效结果。'); return; }
        results.forEach(result => { const output = $$('[data-output]', widget).find(el => el.dataset.output === result.id); output.textContent = number(result.value); });
        announce($('.rw-calc-status', widget), '结果已按当前输入更新；假设与口径见下方。');
      }
      inputs.forEach(input => input.addEventListener('input', calculate));
    }
  });

  // Source links always have real fallback anchors. Native dialogs retain keyboard focus.
  const sourceDialog = $('#rw-source-dialog'), imageDialog = $('#rw-image-dialog');
  document.addEventListener('click', event => {
    const sourceLink = event.target.closest('a[data-source]');
    if (sourceLink && typeof sourceDialog.showModal === 'function') {
      const source = document.getElementById('source-' + sourceLink.dataset.source);
      if (!source) return;
      event.preventDefault(); const copy = source.cloneNode(true); copy.removeAttribute('id'); $$('[id]', copy).forEach(n => n.removeAttribute('id'));
      const body = $('#rw-source-dialog-body'); body.replaceChildren(...Array.from(copy.childNodes)); syncBookmarks(); sourceDialog.showModal();
    }
    const close = event.target.closest('[data-close-dialog]'); if (close) close.closest('dialog').close();
  });
  [sourceDialog, imageDialog].forEach(dialog => dialog.addEventListener('click', event => { if (event.target !== dialog) return; const r = dialog.getBoundingClientRect(); if (event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom) dialog.close(); }));

  let zoom = 1, panX = 0, panY = 0, drag = null;
  const viewport = $('#rw-image-viewport'), large = $('#rw-image-large'), zoomInput = $('#rw-image-zoom');
  function transform() {
    const ratio = large.naturalWidth / (large.naturalHeight || 1) || 1, w = Math.min(viewport.clientWidth, viewport.clientHeight * ratio), h = w / ratio;
    const maxX = Math.max(0, (w * zoom - viewport.clientWidth) / 2), maxY = Math.max(0, (h * zoom - viewport.clientHeight) / 2);
    panX = Math.max(-maxX, Math.min(maxX, panX)); panY = Math.max(-maxY, Math.min(maxY, panY));
    large.style.transform = 'translate(' + panX + 'px,' + panY + 'px) scale(' + zoom + ')'; zoomInput.value = String(zoom); $('#rw-image-scale').textContent = zoom + '×';
  }
  $$('.rw-image').forEach(figure => {
    function open(pointIndex) {
      if (typeof imageDialog.showModal !== 'function') return;
      const image = $('img', figure), widget = figure.closest('.rw-widget'), component = components.get(widget.dataset.component), item = component.items.find(i => component.id + '.' + i.id === figure.dataset.image);
      large.src = image.src; large.alt = image.alt; $('#rw-image-dialog-title').textContent = item.caption || item.alt; zoom = 1; panX = panY = 0;
      const point = Number.isInteger(pointIndex) ? item.points[pointIndex] : null;
      $('#rw-image-description').textContent = point ? point.title + '：' + point.body : item.caption;
      imageDialog.showModal();
      if (point) { zoom = 2; const ratio = image.naturalWidth / image.naturalHeight, w = Math.min(viewport.clientWidth, viewport.clientHeight * ratio); panX = (.5 - point.x / 100) * w * zoom; panY = (.5 - point.y / 100) * w / ratio * zoom; }
      transform();
    }
    $('[data-image-open]', figure)?.addEventListener('click', () => open());
    $$('[data-image-point]', figure).forEach(button => button.addEventListener('click', () => open(Number(button.dataset.imagePoint))));
  });
  zoomInput.addEventListener('input', () => { zoom = Number(zoomInput.value); transform(); });
  $('#rw-image-reset').addEventListener('click', () => { zoom = 1; panX = panY = 0; transform(); });
  large.addEventListener('load', transform);
  viewport.addEventListener('pointerdown', event => { if (zoom <= 1 || event.button !== 0) return; drag = {x: event.clientX, y: event.clientY, px: panX, py: panY}; viewport.setPointerCapture(event.pointerId); event.preventDefault(); });
  viewport.addEventListener('pointermove', event => { if (!drag) return; panX = drag.px + event.clientX - drag.x; panY = drag.py + event.clientY - drag.y; transform(); });
  ['pointerup', 'pointercancel', 'lostpointercapture'].forEach(type => viewport.addEventListener(type, () => { drag = null; }));
  viewport.addEventListener('keydown', event => { const d = {ArrowLeft:[32,0],ArrowRight:[-32,0],ArrowUp:[0,32],ArrowDown:[0,-32]}[event.key]; if (d && zoom > 1) { event.preventDefault(); panX += d[0]; panY += d[1]; transform(); } });

  // Explicit end-of-document handling keeps the last section reachable and current.
  const navLinks = $$('#reader-toc a'), tracked = navLinks.map(link => ({link, element: document.getElementById(decodeURIComponent(link.hash.slice(1)))})).filter(v => v.element);
  let pending = false;
  function progress() {
    pending = false; const max = document.documentElement.scrollHeight - innerHeight;
    $('.rw-progress span').style.width = (max <= 0 ? 100 : Math.min(100, scrollY / max * 100)) + '%';
    let active = tracked[0]; tracked.forEach(item => { if (item.element.getBoundingClientRect().top <= 150) active = item; });
    if (max > 0 && scrollY >= max - 3) active = tracked[tracked.length - 1];
    navLinks.forEach(link => { if (active && active.link === link) link.setAttribute('aria-current', 'true'); else link.removeAttribute('aria-current'); });
  }
  addEventListener('scroll', () => { if (!pending) { pending = true; requestAnimationFrame(progress); } }, {passive:true});
  addEventListener('resize', () => { progress(); if (imageDialog.open) transform(); }); progress();
})();
