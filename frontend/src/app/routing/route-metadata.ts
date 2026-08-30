import { Data, ActivatedRouteSnapshot } from '@angular/router';
import { EventName } from '../api/event-stream';

export type RefreshPredicate = (event: EventName, route: ActivatedRouteSnapshot) => boolean;
export interface ResolverRouteData { loadingLabel: string; refreshOn: RefreshPredicate; }
export const RESOLVER_ROUTE_DATA = 'resolverRouteData';
export const onEvents = (...names: EventName[]): RefreshPredicate => (event) => names.includes(event);
export const routeData = (loadingLabel: string, refreshOn: RefreshPredicate): Data => ({
  [RESOLVER_ROUTE_DATA]: { loadingLabel, refreshOn } satisfies ResolverRouteData,
});
export function resolvedRoute(root: ActivatedRouteSnapshot): ActivatedRouteSnapshot | null {
  let route: ActivatedRouteSnapshot | null = root;
  let match: ActivatedRouteSnapshot | null = null;
  while (route) { if (route.data[RESOLVER_ROUTE_DATA]) match = route; route = route.firstChild; }
  return match;
}