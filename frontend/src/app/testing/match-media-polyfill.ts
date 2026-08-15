/**
 * Teaches jsdom `window.matchMedia`, which it does not implement at all.
 *
 * `lightweight-charts` reaches it through `fancy-canvas`, which watches the
 * device pixel ratio with `matchMedia('all and (resolution: Ndppx)')` the
 * moment a chart is created. jsdom 28 has no `matchMedia` whatsoever, so
 * every spec that renders `TradeChart` — today that is the routing spec, by
 * way of the trade and ticker detail views, which since v25 draw with the
 * same component — produced an unhandled rejection reading
 * "this._window.matchMedia is not a function".
 *
 * Those rejections did not fail anything, which is the reason to fix them
 * rather than live with them: seven errors that are always in the output are
 * seven errors nobody reads, and the eighth one will be real.
 *
 * `addListener`/`removeListener` are here deliberately even though they are
 * deprecated — fancy-canvas calls exactly those, with a comment saying it
 * does so for IE. The modern `addEventListener` pair is provided too so a
 * future caller does not find half an object.
 *
 * What this stands in for is only the shape of the API. No query is ever
 * evaluated: `matches` is always false and no listener is ever invoked, so a
 * test must not assert that a media query matched, or changed — it would be
 * proving something about this file instead. Charts under test are therefore
 * fixed at the initial `devicePixelRatio` and never learn about a change,
 * which is what we want from a headless DOM anyway.
 *
 * Idempotent, and a no-op in any environment that has the real thing.
 */
export function installMatchMediaPolyfill(): void {
  if (typeof window.matchMedia === 'function') return;

  window.matchMedia = function matchMedia(query: string): MediaQueryList {
    const list: MediaQueryList = {
      media: query,
      matches: false,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    };
    return list;
  };
}
