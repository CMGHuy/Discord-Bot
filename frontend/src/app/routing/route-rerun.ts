import { ActivatedRouteSnapshot, Params } from '@angular/router';

/** Values compared as data: a repeated query key arrives as an array. */
function sameValue(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

function sameParams(a: Params, b: Params, ignore: string | null): boolean {
  const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
  return [...keys].every((key) => key === ignore || sameValue(a[key], b[key]));
}

/**
 * A `runGuardsAndResolvers` rule: re-run on every navigation (like
 * `'always'`) except one whose only change is the query parameter `name`
 * — v179 §6b.8.
 *
 * The Dashboard's trade drawer writes `?trade=<id>` as a pushed history entry.
 * Under `'always'` that push re-ran the route resolver and refetched the
 * page, which the spec forbids (§3.2: the drawer fetches nothing). An
 * identical URL still returns `true`: `RouteRefreshService` refreshes a page
 * by re-navigating its own URL with `onSameUrlNavigation: 'reload'`, and that
 * must keep re-resolving.
 */
export function rerunExceptQueryParam(
  name: string,
): (from: ActivatedRouteSnapshot, to: ActivatedRouteSnapshot) => boolean {
  return (from, to) => {
    const onlyNameChanged = sameParams(from.params, to.params, null)
      && !sameValue(from.queryParams[name], to.queryParams[name])
      && sameParams(from.queryParams, to.queryParams, name);
    return !onlyNameChanged;
  };
}
