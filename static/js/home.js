/* Home page: type to search (debounced), suggestions, live filter of the project cards.
   Without JavaScript the form still works: it submits and the server renders the result. */
(function () {
  'use strict';
  var form = document.getElementById('homeForm');
  if (!form || !window.fetch) { return; }
  var input = document.getElementById('homeQ');
  var suggest = document.getElementById('homeSuggest');
  var grid = document.getElementById('homeGrid');
  var skeleton = document.getElementById('homeSkeleton');
  var empty = document.getElementById('homeEmpty');
  var count = document.getElementById('homeCount');
  var selects = form.parentNode.querySelectorAll('select');
  var timer = null;
  var seq = 0;

  function params() {
    var p = new URLSearchParams();
    if (input.value.trim()) { p.set('q', input.value.trim()); }
    Array.prototype.forEach.call(selects, function (s) { if (s.value) { p.set(s.name, s.value); } });
    return p;
  }

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) { node.className = cls; }
    if (text !== undefined) { node.textContent = text; }   // textContent only: project names are never parsed as HTML
    return node;
  }

  function card(p) {
    var a = el('a', 'pcard' + (p.late ? ' is-late' : ''));
    a.href = p.url;
    var top = el('div', 'pcard-top');
    top.appendChild(el('span', 'badge st-' + p.status, p.status_label));
    if (p.late) { top.appendChild(el('span', 'badge st-late', 'Trễ hạn')); }
    else if (p.overdue_tasks) { top.appendChild(el('span', 'badge st-warn', p.overdue_tasks + ' việc quá hạn')); }
    a.appendChild(top);
    a.appendChild(el('h3', '', p.name));
    a.appendChild(el('p', 'pcard-sub', p.client || p.package_name || 'Dự án thi công'));
    var bar = el('div', 'pbar');
    var fill = el('span');
    fill.style.width = Math.min(100, Math.round(p.progress || 0)) + '%';
    bar.appendChild(fill);
    a.appendChild(bar);
    var meta = el('div', 'pcard-meta');
    meta.appendChild(el('b', '', p.progress === null || p.progress === undefined ? 'Chưa cập nhật' : Math.round(p.progress) + '%'));
    meta.appendChild(el('span', '', (p.start_date || '—') + ' → ' + (p.end_date || '—')));
    a.appendChild(meta);
    return a;
  }

  function showSuggestions(list) {
    suggest.textContent = '';
    if (!input.value.trim() || !list.length) { suggest.hidden = true; return; }
    list.slice(0, 6).forEach(function (p) {
      var li = el('li');
      var a = el('a');
      a.href = p.url;
      a.appendChild(el('b', '', p.name));
      a.appendChild(el('small', '', p.client || p.package_name || p.status_label));
      li.appendChild(a);
      suggest.appendChild(li);
    });
    suggest.hidden = false;
  }

  function run() {
    var mine = ++seq;
    skeleton.hidden = false;
    grid.hidden = true;
    empty.hidden = true;
    fetch('/api/projects/search?' + params().toString(), { headers: { Accept: 'application/json' }, credentials: 'same-origin' })
      .then(function (r) { if (!r.ok) { throw new Error(r.status); } return r.json(); })
      .then(function (data) {
        if (mine !== seq) { return; }                    // an older answer arriving late is ignored
        grid.textContent = '';
        data.projects.forEach(function (p) { grid.appendChild(card(p)); });
        count.textContent = '(' + data.total + ')';
        empty.hidden = data.total > 0;
        showSuggestions(data.projects);
        if (history.replaceState) { history.replaceState(null, '', '?' + params().toString()); }
      })
      .catch(function () { if (mine === seq) { form.submit(); } })    // fall back to the server-rendered page
      .then(function () { if (mine === seq) { skeleton.hidden = true; grid.hidden = false; } });
  }

  input.addEventListener('input', function () { clearTimeout(timer); timer = setTimeout(run, 300); });
  Array.prototype.forEach.call(selects, function (s) { s.addEventListener('change', run); });
  form.addEventListener('submit', function (e) { e.preventDefault(); clearTimeout(timer); run(); });
  document.addEventListener('click', function (e) { if (!form.contains(e.target)) { suggest.hidden = true; } });
  input.addEventListener('keydown', function (e) { if (e.key === 'Escape') { suggest.hidden = true; } });
})();
