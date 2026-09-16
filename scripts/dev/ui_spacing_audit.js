// v89 spec §4.3 -- measures the gap between sibling panels on the current admin
// page. Paste into the browser console (or Playwright browser_evaluate as
// `() => { ...this file... }`). Needs no credentials: it reads the page you are on.
//
// Every visible child of a stacking container is compared with its nearest
// neighbour below (same column) and to its right (same row). Any gap that is
// not the computed --section-gap is an offender. Zero-height and
// display:contents children are skipped, which is what those hosts are for.
(() => {
  const root = getComputedStyle(document.documentElement);
  const expected = parseFloat(root.getPropertyValue('--section-gap')) ||
    parseFloat(getComputedStyle(document.body).getPropertyValue('--section-gap'));
  const containers = [
    ...document.querySelectorAll('.workspace-content > :not(router-outlet)'),
    ...document.querySelectorAll('.sb-stack, .sb-row, .panels, .chart-grid, .bottom-row, .split'),
  ];
  const visibleChildren = (el) => [...el.children].flatMap((c) => {
    const style = getComputedStyle(c);
    if (style.display === 'contents') return visibleChildren(c);
    const r = c.getBoundingClientRect();
    return style.display === 'none' || r.height < 1 || r.width < 1 ? [] : [{ el: c, r }];
  });
  const name = (el) => el.tagName.toLowerCase() + (el.classList.length ? '.' + [...el.classList].join('.') : '');
  const offenders = [];
  let checked = 0;
  for (const container of new Set(containers)) {
    const kids = visibleChildren(container);
    for (const a of kids) {
      let below = null;
      let right = null;
      for (const b of kids) {
        if (a === b) continue;
        const hOverlap = Math.min(a.r.right, b.r.right) - Math.max(a.r.left, b.r.left);
        const vOverlap = Math.min(a.r.bottom, b.r.bottom) - Math.max(a.r.top, b.r.top);
        const dy = b.r.top - a.r.bottom;
        const dx = b.r.left - a.r.right;
        if (hOverlap > 40 && dy >= -1 && (below === null || dy < below.gap)) below = { b, gap: dy };
        if (vOverlap > 20 && dx >= -1 && (right === null || dx < right.gap)) right = { b, gap: dx };
      }
      for (const [dir, hit] of [['below', below], ['right', right]]) {
        if (!hit) continue;
        checked += 1;
        if (Math.abs(hit.gap - expected) > 1) {
          offenders.push(`${name(container)}: ${name(a.el)} -> ${dir} ${name(hit.b.el)} = ${Math.round(hit.gap)}px`);
        }
      }
    }
  }
  return { path: location.pathname, width: innerWidth, expected, checked, offenders };
})();
