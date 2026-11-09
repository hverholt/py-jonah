// Reflow the embedded Matplotlib SVG when the browser or sidebar changes size.
// The time-series graphs can stretch in x/y, text and the polar diagram can not.
(function () {
  const container = document.getElementById('overview-content');
  if (!container) return;

  const FONT_SCALE = 1.30;  // Enlarge dashboard text by 30%.
  let frame = 0;

  function fitOverview() {
    frame = 0;
    const svg = container.querySelector(':scope > svg');
    if (!svg) return;

    svg.setAttribute('preserveAspectRatio', 'none');
    const box = svg.getBoundingClientRect();
    const viewBox = svg.viewBox.baseVal;
    if (!box.width || !box.height || !viewBox.width || !viewBox.height) return;

    // Move the long wind readout into ordinary HTML so it can wrap on narrow screens.
    const readout = [...svg.querySelectorAll('g[id^="text_"]')].find(group => {
      const text = group.textContent.trim();
      return text.startsWith('Wind speed:') || text.startsWith('Wind: No') ||
             text.startsWith('Wind: Weather') || text.startsWith('Wind: ODR');
    });
    let readoutElement = container.querySelector('#overview-wind-readout');
    if (readout) {
      readout.style.display = 'none';
      if (!readoutElement) {
        readoutElement = document.createElement('div');
        readoutElement.id = 'overview-wind-readout';
        container.appendChild(readoutElement);
      }
      const windText = readout.textContent.trim();
      if (readoutElement.textContent !== windText) {
        readoutElement.textContent = windText;
      }
    } else if (readoutElement) {
      readoutElement.remove();
    }

    const stretch = (box.width / viewBox.width) / (box.height / viewBox.height);
    const textCorrection = 1 / stretch;

    // Find the polar panel by its title, not an assumed Matplotlib axes number.
    const polar = [...svg.querySelectorAll('g[id^="axes_"]')].find(group =>
      [...group.querySelectorAll('text')].some(text =>
        text.textContent.trim() === 'CURRENT DIRECTION'
      )
    );

    // Text is rendered at fixed positions by Matplotlib. Correct the SVG's
    // nonuniform scaling, then enlarge each label without shifting its anchor.
    for (const label of svg.querySelectorAll('g[id^="text_"]')) {
      label.style.transformBox = 'fill-box';
      label.style.transformOrigin = 'center';
      // The polar group gets its own aspect-ratio correction below.
      label.style.transform = polar && polar.contains(label)
        ? `scale(${FONT_SCALE})`  // Updated below after polar geometry is fitted.
        : `scale(${textCorrection * FONT_SCALE}, ${FONT_SCALE})`;
    }

    // Unlike the plotting axes, the original vector logo must not stretch.
    const logo = svg.querySelector('#dashboard-logo');
    if (logo) {
      logo.style.transformBox = 'fill-box';
      logo.style.transformOrigin = 'center';
      logo.style.transform = `scaleX(${textCorrection})`;
    }

    // Keep the enlarged main heading inside its available header space.
    // On smaller desktops there is not room for a full 30% increase beside
    // the logo, so the title scales down just enough to avoid clipping.
    const title = [...svg.querySelectorAll('g[id^="text_"]')].find(group =>
      group.textContent.includes('LIVE CURRENT MONITOR')
    );
    if (title) {
      title.style.transform = 'none';
      const original = title.getBoundingClientRect();
      const logoLeft = logo ? logo.getBoundingClientRect().left - 16 : box.right - 16;
      const available = Math.max(1, logoLeft - original.left);
      const titleScale = Math.min(FONT_SCALE, available / (original.width * textCorrection));
      title.style.transformOrigin = 'left center';
      title.style.transform = `scale(${textCorrection * titleScale}, ${titleScale})`;
    }

    // The changing source/refresh subtitle is unusually long. Keep it legible
    // without allowing it to collide with the plot's top-right depth legend.
    const subtitle = [...svg.querySelectorAll('g[id^="text_"]')].find(group =>
      group.textContent.includes('Viewing last') && group.textContent.includes('Auto-refresh')
    );
    if (subtitle) {
      subtitle.style.transform = 'none';
      const original = subtitle.getBoundingClientRect();
      const depthLegend = [...svg.querySelectorAll('g[id^="text_"]')].find(group =>
        group.textContent.trim() === 'Current depth'
      );
      const rightLimit = depthLegend
        ? depthLegend.getBoundingClientRect().left - 12
        : box.right - 16;
      const available = Math.max(1, rightLimit - original.left);
      const subtitleScale = Math.min(FONT_SCALE, available / (original.width * textCorrection));
      subtitle.style.transformOrigin = 'left center';
      subtitle.style.transform = `scale(${textCorrection * subtitleScale}, ${subtitleScale})`;
    }

    if (polar) {
      // Matplotlib draws the circle at its own centre. Measure that circle,
      // NOT the whole axes group: the legend and enlarged labels can extend
      // far outside it, causing the old code to shrink and displace the plot.
      const circle = polar.querySelector(':scope > g[id^="patch_"] > path');
      const info = [...svg.querySelectorAll('g[id^="axes_"]')].find(group =>
        group !== polar && group.textContent.includes('LATEST MEASUREMENTS')
      );
      const panel = info && info.querySelector(':scope > g[id^="patch_"] > path');
      if (circle) {
        const bounds = circle.getBBox();  // Source SVG coordinates (no CSS scaling).
        const centerX = bounds.x + bounds.width / 2;
        const centerY = bounds.y + bounds.height / 2;
        const scaleX = box.width / viewBox.width;
        const scaleY = box.height / viewBox.height;

        // Restrict only the *circle* to the right column, leaving room for
        // compass labels. At normal desktop widths the circle stays full-size.
        const rightWidth = (panel ? panel.getBBox().width : viewBox.width * 0.305) * scaleX;
        const availableCircleWidth = Math.max(1, rightWidth - 36);
        const circleDiameter = Math.max(bounds.width, bounds.height) * scaleY;
        const fit = Math.min(1, availableCircleWidth / circleDiameter);

        // Compensate for the nonuniform stretching of the outer SVG, around
        // the ACTUAL polar centre (not the axes+legend bounding-box centre).
        // A modest upward shift recovers space lost on unusually tall screens.
        const upwardPx = Math.min(18, Math.max(0, (1 - fit) * 140));
        const sx = textCorrection * fit;
        const sy = fit;
        const tx = centerX * (1 - sx);
        const ty = centerY * (1 - sy) - upwardPx / scaleY;
        polar.style.removeProperty('transform');
        polar.style.removeProperty('transform-box');
        polar.style.removeProperty('transform-origin');
        polar.setAttribute('transform', `matrix(${sx} 0 0 ${sy} ${tx} ${ty})`);

        // Compensate for any necessary circle fitting so polar fonts retain
        // the same +30% size as other labels rather than shrinking with it.
        for (const label of polar.querySelectorAll('g[id^="text_"]')) {
          label.style.transform = `scale(${FONT_SCALE / fit})`;
        }

        // The original Matplotlib legend is placed outside the lower-right
        // edge of the polar axes. Once fonts are larger, keep it inside the
        // right panel instead of letting the SVG/page clip its labels.
        const legend = polar.querySelector(':scope > g[id^="legend_"]');
        if (legend) {
          legend.removeAttribute('transform');  // No drift on repeated resizes.
          const legendRect = legend.getBoundingClientRect();
          const panelRight = panel
            ? box.left + (panel.getBBox().x + panel.getBBox().width - viewBox.x) * scaleX
            : box.right;
          const rightLimit = Math.min(box.right - 10, panelRight - 5);
          const overflow = Math.max(0, legendRect.right - rightLimit);
          if (overflow > 0) {
            legend.setAttribute('transform', `translate(${-overflow / (scaleY * fit)} 0)`);
          }
        }
      }
    }
  }

  function requestFit() {
    if (!frame) frame = requestAnimationFrame(fitOverview);
  }

  new ResizeObserver(requestFit).observe(container);
  // The automatic browser update replaces the SVG, so fit each new one too.
  new MutationObserver(requestFit).observe(container, {childList: true});
  window.addEventListener('resize', requestFit);
  requestFit();
})();
