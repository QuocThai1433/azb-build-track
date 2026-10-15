/* Draws the dependency arrows on the Gantt chart as one SVG laid over the grid. */
(function () {
  var grid = document.getElementById('ganttGrid');
  var holder = document.getElementById('ganttDeps');
  if (!grid || !holder) return;
  var deps;
  try { deps = JSON.parse(holder.textContent || '[]'); } catch (e) { return; }
  if (!deps.length) return;
  var NS = 'http://www.w3.org/2000/svg';

  function draw() {
    var old = grid.querySelector('svg.gantt-links');
    if (old) old.remove();
    var box = grid.getBoundingClientRect();
    var svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('class', 'gantt-links');
    svg.setAttribute('width', grid.scrollWidth);
    svg.setAttribute('height', grid.scrollHeight);
    var defs = document.createElementNS(NS, 'defs');
    defs.innerHTML = '<marker id="gArrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto">' +
      '<path d="M0 0L10 5L0 10z" fill="#4a5a73"/></marker>';
    svg.appendChild(defs);

    function pos(id) {
      var el = grid.querySelector('.gantt-bar[data-task="' + id + '"]');
      if (!el) return null;
      var r = el.getBoundingClientRect();
      return { l: r.left - box.left, r: r.right - box.left, y: r.top - box.top + r.height / 2 };
    }

    deps.forEach(function (d) {
      var a = pos(d.p), b = pos(d.s);
      if (!a || !b) return;
      var fromX = (d.t === 'SS' || d.t === 'SF') ? a.l : a.r;
      var toX = (d.t === 'FF' || d.t === 'SF') ? b.r : b.l;
      var dir = (d.t === 'FF' || d.t === 'SF') ? 1 : -1;
      var elbow = dir === -1 ? Math.min(fromX, toX) - 8 : Math.max(fromX, toX) + 8;
      if (d.t === 'FS' && toX > fromX + 12) elbow = fromX + 6;
      var path = document.createElementNS(NS, 'path');
      path.setAttribute('d', 'M' + fromX + ' ' + a.y + ' H' + elbow + ' V' + b.y + ' H' + toX);
      path.setAttribute('fill', 'none');
      path.setAttribute('stroke', '#4a5a73');
      path.setAttribute('stroke-width', '1');
      path.setAttribute('marker-end', 'url(#gArrow)');
      svg.appendChild(path);
    });
    grid.appendChild(svg);
  }

  draw();
  window.addEventListener('resize', draw);
})();
