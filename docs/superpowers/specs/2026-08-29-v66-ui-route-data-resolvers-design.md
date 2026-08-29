# UI route data resolvers design

Version: ui 1.9.2; bot 1.4.5

Bump: ui minor (1.9.x to 1.10.0)

Edge: none (integrity)

## Goal

Every authenticated Angular workspace and detail view renders from fresh route-resolved data rather than starting its initial request after component creation. Loading appears only for slow requests, failures use the workspace's existing error state, and live updates converge the UI on server-authoritative data.

## Scope

This applies to Dashboard; Trades and Trade Detail; Analytics; Calendar; Watchlist and Ticker Detail; Risk; System; and Versions. It also applies when relevant query parameters change and after a successful mutation. Authentication remains a pre-loading gate through the existing `canMatch` guard.

## Architecture

Add a central route-data coordinator that owns resolver navigation and refresh policy. Each protected route declares a resolver for only its initially visible data. Resolver-compatible store APIs complete when their initial API request settles; stores stop issuing their first request from `onInit` effects.

The coordinator is the only owner of event-driven route refreshes. It listens to live server events, debounces a burst into one refresh after the final event, and re-navigates the active URL to run the same resolver flow. Newer navigation or refresh cancels obsolete in-flight work, so only the newest target commits route-ready state.

The shell owns navigation-progress presentation. The sidebar and header stay visible. Resolution exceeding one second dims the active outlet and adds a non-interactive, route-aware loading overlay above it. Faster transitions show no loading treatment. The overlay clears when navigation completes, fails, or is cancelled.

## Route data contract

Each resolver loads only initially visible data; secondary tabs, optional charts, and non-visible support data remain demand-loaded.

| Route | Blocking data |
|---|---|
| Dashboard | Dashboard payload |
| Trades | List payload for the URL's filters, sorting, and page |
| Trade Detail | Selected trade detail |
| Analytics | Selected or default tab payload only |
| Calendar | Selected month |
| Watchlist | Ticker list |
| Ticker Detail | Selected ticker's primary quote/chart payload |
| Risk | Risk payload |
| System | Selected or default tab payload only |
| Versions | Version timeline |

Every initial route visit refetches from the server. Relevant query-parameter changes rerun the resolver; query state remains the durable source for the data view.

## Outcomes and error handling

On successful resolution, the route activates with ready store state and renders real data immediately. On a non-auth API failure, the route still activates and its existing inline error and retry UI renders from the store failure state. First entry never represents absent data as a valid empty result. Later refreshes may retain prior data only where the existing workspace contract supports stale-while-error.

An expired session redirects to login while preserving the requested URL for return after authentication. There is no artificial resolver timeout; network completion, cancellation, and the ordinary API error path decide the outcome.

## Live changes, mutations, and drafts

Navigation, query changes, live updates, and post-mutation refreshes share the resolver path so their loading, cancellation, authentication, and error behavior cannot drift. Successful mutations invalidate affected route data and schedule the same refresh.

Stores with unsaved local edits, notably System settings and trade notes, expose draft state to the coordinator. An event-driven refresh never overwrites a draft; the workspace preserves local edits, shows a data-changed notice, and offers an explicit server-data reload. Only that explicit action replaces the draft.

## Parallelisation

Sequential throughout for the shared coordinator, route configuration, shell overlay, and store contract: each later change consumes the shared resolver and refresh API introduced before it. Route migration tests may run in parallel only after that contract exists, provided each task has disjoint workspace and spec files.

## Verification and rollout

1. Add router tests covering resolver presence, activation after initial resolution, and reruns for relevant query changes.
2. Test the shell overlay's one-second delay, fast no-flicker path, dimmed non-interactive outlet, cancellation, and cleanup after errors.
3. Test success; non-auth error activation; expired-session return URL; and suppression of stale request commits after rapid navigation.
4. Test event-burst debouncing, mutation invalidation, and one refresh after the final event.
5. Test draft preservation and explicit replacement following live changes.
6. Migrate Dashboard first to validate the shared contract, then migrate remaining routes. Remove a store's first-load and event-driven initialization effects only after its route resolver coverage is in place.

## Non-goals

- Blocking navigation on secondary tabs or optional chart data.
- Rendering a stale cache as a new route's initial state.
- Replacing workspace-level error UI with a global error page.
- Automatically overwriting unsaved local edits during a refresh.
