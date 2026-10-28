/* Reopen where you left off: remembers the current page (the URL hash) and how far each scrolling panel was
   scrolled, and restores both on the next start when no page was asked for (the desktop app always starts
   without a hash). Load it before app.js: the hash has to be back in place before the app's first route().
   A desktop app is often closed without an unload event, so the state is saved on every navigation and while
   scrolling, not only when the window goes away. */
(() => {
  const KEY = 'math2viz.resume';
  // the panels whose scroll position is worth keeping (list columns, detail panes, the reader)
  const PANELS = ['#tocTree', '#pagesWrap', '#side', '#v-overview', '#cardList .lst', '#cardDetail', '#graphSide',
    '#v-blind', '#qList .lst', '#qDetail'];

  let saved = null;
  try { saved = JSON.parse(localStorage.getItem(KEY) || 'null'); } catch (e) { /* nothing saved */ }
  if (!location.hash && saved && saved.hash) history.replaceState(null, '', saved.hash);

  const snapshot = () => {
    const scroll = {};
    for (const s of PANELS) {
      const el = document.querySelector(s);
      if (el && el.offsetParent !== null && (el.scrollTop || el.scrollLeft)) scroll[s] = [el.scrollTop, el.scrollLeft];
    }
    try { localStorage.setItem(KEY, JSON.stringify({ hash: location.hash, scroll })); } catch (e) { /* storage unavailable */ }
  };
  let timer = null;
  const later = (ms = 400) => { clearTimeout(timer); timer = setTimeout(snapshot, ms); };

  // put the panels back once the first page is drawn; images and fonts may still change heights, so try a few
  // times, and stop as soon as the reader moves on their own
  let touched = false;
  const restore = () => {
    if (touched || !saved || saved.hash !== location.hash) return;
    for (const [s, [top, left]] of Object.entries(saved.scroll || {})) {
      const el = document.querySelector(s);
      if (el) { el.scrollTop = top; el.scrollLeft = left; }
    }
  };
  addEventListener('DOMContentLoaded', () => {
    requestAnimationFrame(restore);
    [250, 800, 2000].forEach(ms => setTimeout(restore, ms));
    setTimeout(() => { saved = null; }, 2100);
  });
  ['wheel', 'pointerdown', 'keydown', 'touchstart'].forEach(t => addEventListener(t, () => { touched = true; }, { capture: true, passive: true }));

  addEventListener('hashchange', () => later(50));
  document.addEventListener('scroll', () => later(), { capture: true, passive: true });
  addEventListener('pagehide', snapshot);
  document.addEventListener('visibilitychange', () => { if (document.hidden) snapshot(); });
})();
