import { Observable, throwError } from 'rxjs';
import { describe, expect, it, vi } from 'vitest';

import { ApiError } from '../api/api-error';
import { routeRequest } from './route-request';

describe('routeRequest', () => {
  it('settles a non-auth error after projecting it into store state', () => {
    const seen: ApiError[] = [];
    const values: void[] = [];
    routeRequest(throwError(() => new ApiError('unavailable', 0, 'down')), {
      start: vi.fn(), next: vi.fn(), error: (error) => seen.push(error),
    }).subscribe((value) => values.push(value));
    expect(seen).toHaveLength(1);
    expect(values).toEqual([undefined]);
  });

  it('rethrows auth failures and preserves cancellation', () => {
    let tornDown = false;
    const source = new Observable<never>(() => () => { tornDown = true; });
    const sub = routeRequest(source, { start: vi.fn(), next: vi.fn(), error: vi.fn() }).subscribe();
    sub.unsubscribe();
    expect(tornDown).toBe(true);
  });
});