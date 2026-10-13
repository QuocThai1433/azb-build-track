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

  document.querySelectorAll('[data-confirm]').forEach((element) => {
    element.addEventListener('click', (event) => {
      const message = element.getAttribute('data-confirm') || 'Bạn có chắc chắn muốn tiếp tục?';
      if (!window.confirm(message)) event.preventDefault();
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
