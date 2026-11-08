const pageNames = ['overview', 'profiles', 'roses'];
let activePage = null;
let displayedVersion = document.querySelector('meta[name="dashboard-generated"]').content;
let lastModified = null;
let checking = false;


function initializePage(page) {
  if (page === 'overview') return;

  const section = document.getElementById(`page-${page}`);
  if (section.dataset.initialized) return;

  section.innerHTML = '<p class="empty-message">Will be added later.</p>';
  section.dataset.initialized = 'true';
}


function showPage(name) {
  const page = pageNames.includes(name) ? name : 'overview';
  const previousPage = activePage;
  activePage = page;
  for (const item of pageNames) {
    document.getElementById(`page-${item}`).hidden = item !== page;
  }
  for (const link of document.querySelectorAll('.nav-link')) {
    if (link.dataset.page === page) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  }
  initializePage(page);
  if (page === 'overview' && previousPage !== null && previousPage !== page) {
    checkDashboard();
  }
}

window.addEventListener('hashchange', () => showPage(location.hash.slice(1)));
showPage(location.hash.slice(1));

async function checkDashboard() {
  if (activePage !== 'overview' || checking) return;
  checking = true;
  try {
    const url = new URL(window.location.href);
    url.searchParams.set('_', Date.now().toString());
    const head = await fetch(url, {method: 'HEAD', cache: 'no-store'});
    if (!head.ok) throw new Error(`HTTP ${head.status}`);
    const modified = head.headers.get('last-modified');
    if (modified && modified === lastModified) return;

    const response = await fetch(url, {cache: 'no-store'});
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const html = await response.text();
    const updated = new DOMParser().parseFromString(html, 'text/html');
    const newVersion = updated.querySelector('meta[name="dashboard-generated"]')?.content;
    const newSvg = updated.querySelector('#overview-content > svg');
    if (newVersion && newSvg) {
      if (newVersion !== displayedVersion) {
        const currentSvg = document.querySelector('#overview-content > svg');
        if (currentSvg) currentSvg.replaceWith(document.importNode(newSvg, true));
        displayedVersion = newVersion;
        document.querySelector('meta[name="dashboard-generated"]').content = newVersion;
      }
      lastModified = modified;
    }
  } catch (error) {
    console.warn('Dashboard update failed:', error);
  } finally {
    checking = false;
  }
}

setInterval(checkDashboard, __WEB_POLL_MS__);
