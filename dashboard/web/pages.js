const pageNames = ['overview', 'profiles', 'amplitude', 'roses'];
const plotIds = {
  polar: 'polar-content',
  timeseries: 'timeseries-content',
  profiles: 'profiles-content',
  amplitude: 'amplitude-content',
};
const pendingPlots = new Map();
let activePage = null;
let displayedVersion = document.querySelector('meta[name="dashboard-generated"]').content;
let lastModified = null;
let checking = false;

function syncPlotFonts() {
  const styles = getComputedStyle(document.documentElement);
  const regular = parseFloat(styles.getPropertyValue('--font-regular')) || 12;

  for (const svg of document.querySelectorAll('.timeseries-plot svg, .polar-plot svg, .profiles-chart svg')) {
    if (svg.getBoundingClientRect().width === 0) continue;
    const matrix = svg.getScreenCTM();
    if (!matrix) continue;
    const pixelsPerUnit = Math.hypot(matrix.a, matrix.b);
    if (!Number.isFinite(pixelsPerUnit) || pixelsPerUnit <= 0) continue;
    svg.style.setProperty('--svg-font-regular', `${regular / pixelsPerUnit}px`);
  }
}

const plotFontObserver = new ResizeObserver(syncPlotFonts);
function observePlotFonts() {
  plotFontObserver.disconnect();
  for (const container of document.querySelectorAll('.timeseries-plot, .polar-plot, .profiles-chart')) {
    plotFontObserver.observe(container);
  }
  syncPlotFonts();
}
window.addEventListener('resize', syncPlotFonts);

async function loadPlot(name, version) {
  const target = document.getElementById(plotIds[name]);
  if (!target || !target.dataset.src || target.dataset.loadedVersion === version) return;

  const existing = pendingPlots.get(name);
  if (existing && existing.target === target && existing.version === version) {
    return existing.promise;
  }

  const promise = (async () => {
    try {
      const source = target.dataset.src;
      const url = new URL(source, document.baseURI);
      const response = await fetch(url, {cache: 'no-store'});
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const markup = await response.text();
      if (!target.isConnected || displayedVersion !== version || target.dataset.src !== source) return;
      target.innerHTML = markup;
      target.dataset.loadedVersion = version;
      syncPlotFonts();
    } catch (error) {
      if (target.isConnected && displayedVersion === version) {
        if (!target.querySelector('svg')) {
          target.innerHTML = '<div class="plot-loading" role="status">Plot unavailable.</div>';
        }
        console.warn(`Failed to load ${name}:`, error);
      }
    } finally {
      if (pendingPlots.get(name)?.promise === promise) pendingPlots.delete(name);
    }
  })();

  pendingPlots.set(name, {target, version, promise});
  return promise;
}

async function loadOverview(version) {
  await loadPlot('polar', version);
  if (activePage === 'overview' && displayedVersion === version) {
    await loadPlot('timeseries', version);
  }
}

function loadActivePage() {
  const version = displayedVersion;
  if (activePage === 'overview') void loadOverview(version);
  else if (activePage === 'profiles' || activePage === 'amplitude') {
    void loadPlot(activePage, version);
  }
}

function showPage(name) {
  const page = pageNames.includes(name) ? name : 'overview';
  const previous = activePage;
  activePage = page;
  for (const item of pageNames) {
    const section = document.getElementById(`page-${item}`);
    section.hidden = item !== page;
    if (item === 'roses' && !section.dataset.initialized) {
      section.innerHTML = '<div class="empty-state">Plots will be added later.</div>';
      section.dataset.initialized = 'true';
    }
  }
  for (const link of document.querySelectorAll('.nav-link')) {
    if (link.dataset.page === page) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  }
  syncPlotFonts();
  loadActivePage();
  if (previous && previous !== page && page !== 'roses') void checkDashboard();
}

function updateDashboardMetadata(updated) {
  const current = document.getElementById('overview-content');
  const incoming = updated.getElementById('overview-content');
  if (!current || !incoming) return;

  for (const selector of ['.dashboard-header', '.measurement-list', '.polar-legend']) {
    const oldElement = current.querySelector(selector);
    const newElement = incoming.querySelector(selector);
    if (oldElement && newElement) {
      oldElement.replaceWith(document.importNode(newElement, true));
    }
  }

  for (const id of Object.values(plotIds)) {
    const target = document.getElementById(id);
    const next = updated.getElementById(id);
    if (target && next) target.dataset.src = next.dataset.src;
  }
}

async function checkDashboard() {
  if (activePage === 'roses' || checking) return;
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
    const updated = new DOMParser().parseFromString(await response.text(), 'text/html');
    const newVersion = updated.querySelector('meta[name="dashboard-generated"]')?.content;
    if (newVersion && newVersion !== displayedVersion) {
      updateDashboardMetadata(updated);
      displayedVersion = newVersion;
      document.querySelector('meta[name="dashboard-generated"]').content = newVersion;
      loadActivePage();
    }
    lastModified = modified;
  } catch (error) {
    console.warn('Dashboard update failed:', error);
  } finally {
    checking = false;
  }
}

window.addEventListener('hashchange', () => showPage(location.hash.slice(1)));
showPage(location.hash.slice(1));
observePlotFonts();
setInterval(checkDashboard, __WEB_POLL_MS__);
