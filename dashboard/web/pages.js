// The dashboard is a single generated HTML file; no chart library is loaded online.
const pageNames = ['overview', 'profiles', 'amplitude', 'roses'];
let activePage = null;
let displayedVersion = document.querySelector('meta[name="dashboard-generated"]').content;
let lastModified = null;
let checking = false;

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
  if ((page === 'overview' || page === 'profiles' || page === 'amplitude') && previous && previous !== page) checkDashboard();
}

// Plot positions remain in SVG coordinates. Font sizes are converted from
// CSS pixels on each resize so the apparent size matches the HTML exactly.
function syncPlotFonts() {
  const styles = getComputedStyle(document.documentElement);
  const regular = parseFloat(styles.getPropertyValue('--font-regular')) || 11.2;
  const heading = parseFloat(styles.getPropertyValue('--font-heading')) || 16.8;

  for (const svg of document.querySelectorAll('.timeseries-plot svg, .polar-plot svg, .profiles-chart svg')) {
    if (svg.getBoundingClientRect().width === 0) continue; // hidden variants
    const matrix = svg.getScreenCTM();
    if (!matrix) continue;
    const pixelsPerUnit = Math.hypot(matrix.a, matrix.b);
    if (!Number.isFinite(pixelsPerUnit) || pixelsPerUnit <= 0) continue;

    svg.style.setProperty('--svg-font-regular', `${regular / pixelsPerUnit}px`);
    svg.style.setProperty('--svg-font-heading', `${heading / pixelsPerUnit}px`);
    for (const text of svg.querySelectorAll('text')) {
      text.classList.toggle('svg-heading', text.textContent.trim() === 'CURRENT DIRECTION');
    }
  }
}

const plotFontObserver = new ResizeObserver(syncPlotFonts);
function observePlotFonts() {
  plotFontObserver.disconnect(); // do not keep removed panels after live updates
  for (const container of document.querySelectorAll('.timeseries-plot, .polar-plot, .profiles-chart')) {
    plotFontObserver.observe(container);
  }
  syncPlotFonts();
}
window.addEventListener('resize', syncPlotFonts);


window.addEventListener('hashchange', () => showPage(location.hash.slice(1)));
showPage(location.hash.slice(1));
observePlotFonts();

async function checkDashboard() {
  if ((activePage !== 'overview' && activePage !== 'profiles' && activePage !== 'amplitude') || checking) return;
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
    const newContent = updated.getElementById('overview-content');
    const newProfiles = updated.getElementById('profiles-content');
    const newAmplitude = updated.getElementById('amplitude-content');
    if (newVersion && newContent) {
      if (newVersion !== displayedVersion) {
        const current = document.getElementById('overview-content');
        // Replace both SVGs, readings and status together in the DOM.
        current.replaceWith(document.importNode(newContent, true));

        const currentProfiles = document.getElementById('profiles-content');
        if (currentProfiles && newProfiles) {
          currentProfiles.replaceWith(document.importNode(newProfiles, true));
        }
        const currentAmplitude = document.getElementById('amplitude-content');
        if (currentAmplitude && newAmplitude) {
          currentAmplitude.replaceWith(document.importNode(newAmplitude, true));
        }
        observePlotFonts();
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
