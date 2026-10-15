document.addEventListener('DOMContentLoaded', () => {
  const menuButton = document.getElementById('mobileMenu');
  const sidebar = document.getElementById('sidebar');
  if (menuButton && sidebar) {
    const backdrop = document.createElement('div');
    backdrop.className = 'sidebar-backdrop';
    backdrop.setAttribute('aria-hidden', 'true');
    document.body.appendChild(backdrop);
    const closeMenu = () => { sidebar.classList.remove('open'); backdrop.classList.remove('show'); menuButton.setAttribute('aria-expanded', 'false'); };
    const openMenu = () => { sidebar.classList.add('open'); backdrop.classList.add('show'); menuButton.setAttribute('aria-expanded', 'true'); };
    menuButton.setAttribute('aria-expanded', 'false');
    menuButton.addEventListener('click', () => sidebar.classList.contains('open') ? closeMenu() : openMenu());
    backdrop.addEventListener('click', closeMenu);
    document.addEventListener('keydown', (event) => { if (event.key === 'Escape') closeMenu(); });
    sidebar.querySelectorAll('a').forEach((link) => link.addEventListener('click', () => { if (window.matchMedia('(max-width: 980px)').matches) closeMenu(); }));
  }

  document.querySelectorAll('.flash-close').forEach((button) => {
    button.addEventListener('click', () => button.closest('.flash')?.remove());
  });

  // Hộp xác nhận dùng chung (thay cho window.confirm của trình duyệt).
  const approved = new WeakSet();
  const askConfirm = (opts) => new Promise((resolve) => {
    const danger = opts.danger;
    const overlay = document.createElement('div');
    overlay.className = 'azb-confirm-overlay';
    overlay.innerHTML = '<div class="azb-confirm" role="alertdialog" aria-modal="true" aria-labelledby="azbConfirmTitle">' +
      '<div class="azb-confirm-icon ' + (danger ? 'is-danger' : '') + '" aria-hidden="true">' + (danger ? '!' : '?') + '</div>' +
      '<div class="azb-confirm-body"><h3 id="azbConfirmTitle"></h3><p></p></div>' +
      '<div class="azb-confirm-actions"><button type="button" class="btn btn-outline" data-no></button>' +
      '<button type="button" class="btn ' + (danger ? 'btn-danger' : 'btn-primary') + '" data-yes></button></div></div>';
    overlay.querySelector('h3').textContent = opts.title;
    overlay.querySelector('p').textContent = opts.message;
    overlay.querySelector('[data-no]').textContent = opts.cancel;
    overlay.querySelector('[data-yes]').textContent = opts.ok;
    const previous = document.activeElement;
    const done = (value) => {
      document.removeEventListener('keydown', onKey, true);
      overlay.remove();
      if (previous && previous.focus) previous.focus();
      resolve(value);
    };
    const onKey = (event) => {
      if (event.key === 'Escape') { event.preventDefault(); done(false); }
      else if (event.key === 'Tab') {
        const btns = overlay.querySelectorAll('button');
        const first = btns[0], last = btns[btns.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }
    };
    overlay.addEventListener('click', (event) => { if (event.target === overlay) done(false); });
    overlay.querySelector('[data-no]').addEventListener('click', () => done(false));
    overlay.querySelector('[data-yes]').addEventListener('click', () => done(true));
    document.addEventListener('keydown', onKey, true);
    document.body.appendChild(overlay);
    requestAnimationFrame(() => overlay.classList.add('show'));
    overlay.querySelector('[data-yes]').focus();
  });
  window.azbConfirm = askConfirm;

  document.querySelectorAll('[data-confirm]').forEach((element) => {
    element.addEventListener('click', (event) => {
      if (approved.has(element)) { approved.delete(element); return; }
      event.preventDefault();
      const message = element.getAttribute('data-confirm') || 'Bạn có chắc chắn muốn tiếp tục?';
      const danger = /xóa|xoá|hoàn tác|không thể/i.test(message + ' ' + (element.getAttribute('data-confirm-title') || ''));
      askConfirm({
        message,
        danger,
        title: element.getAttribute('data-confirm-title') || (danger ? 'Xác nhận xoá' : 'Xác nhận thao tác'),
        ok: element.getAttribute('data-confirm-ok') || (/xóa|xoá/i.test(message) ? 'Xoá' : 'Xác nhận'),
        cancel: 'Huỷ',
      }).then((yes) => {
        if (!yes) return;
        approved.add(element);
        const form = element.tagName === 'FORM' ? element : element.form || element.closest('form');
        if (element.tagName === 'FORM') element.requestSubmit();
        else if (element.type === 'submit' && form) form.requestSubmit(element);
        else element.click();
      });
    });
  });

  // Sidebar project menu (<details>): close when clicking elsewhere or pressing Escape.
  const projectMenu = document.getElementById('projectMenu');
  if (projectMenu) {
    document.addEventListener('click', (event) => {
      if (projectMenu.open && !projectMenu.contains(event.target)) projectMenu.open = false;
    });
    document.addEventListener('keydown', (event) => { if (event.key === 'Escape') projectMenu.open = false; });
  }

  const fileInput = document.getElementById('workbook');
  const fileName = document.getElementById('fileName');
  if (fileInput && fileName) {
    fileInput.addEventListener('change', () => {
      fileName.textContent = fileInput.files?.[0]?.name || 'Chọn file Excel từ máy tính';
    });
  }

  const progressInput = document.querySelector('input[name="actual_progress"]');
  const progressPreview = document.getElementById('actualProgressPreview');
  if (progressInput && progressPreview) {
    const update = () => {
      const value = Math.max(0, Math.min(100, Number(progressInput.value || 0)));
      progressPreview.style.width = `${value}%`;
    };
    progressInput.addEventListener('input', update);
    update();
  }
});

// Enterprise quick navigation: search available modules and jump directly to them.
document.addEventListener('DOMContentLoaded', () => {
  const input = document.getElementById('globalSearch');
  const results = document.getElementById('searchResults');
  if (!input || !results) return;
  const links = [...document.querySelectorAll('.sidebar .nav-link')]
    .map((a) => ({ label: a.innerText.replace(/\s+/g, ' ').trim(), href: a.href }))
    .filter((item) => item.label && item.href);
  const close = () => { results.hidden = true; results.innerHTML = ''; };
  const render = () => {
    const q = input.value.trim().toLocaleLowerCase('vi');
    if (!q) { close(); return; }
    const matches = links.filter((item) => item.label.toLocaleLowerCase('vi').includes(q)).slice(0, 7);
    results.innerHTML = matches.length
      ? '<div class="result-group">Đi đến chức năng</div>' + matches.map((item) => `<a href="${item.href}">${item.label}<span style="margin-left:auto;color:#9aa8bb">↗</span></a>`).join('')
      : '<div class="no-result">Không tìm thấy chức năng phù hợp.</div>';
    results.hidden = false;
  };
  input.addEventListener('input', render);
  input.addEventListener('focus', render);
  input.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') { close(); input.blur(); }
    if (event.key === 'Enter') {
      const first = results.querySelector('a');
      if (first) window.location.href = first.href;
    }
    if (event.key === 'ArrowDown') {
      const first = results.querySelector('a');
      if (first) { event.preventDefault(); first.focus(); }
    }
  });
  document.addEventListener('click', (event) => {
    if (!event.target.closest('.global-search')) close();
  });
  document.addEventListener('keydown', (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
      event.preventDefault(); input.focus(); input.select();
    }
  });
});
