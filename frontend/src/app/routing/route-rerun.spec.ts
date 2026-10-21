import { ActivatedRouteSnapshot } from '@angular/router';
import { describe, expect, it } from 'vitest';

import { rerunExceptQueryParam } from './route-rerun';

const snap = (queryParams: Record<string, unknown>, params: Record<string, string> = {}) =>
  ({ params, queryParams }) as unknown as ActivatedRouteSnapshot;

describe('rerunExceptQueryParam (v179 §6b.8)', () => {
  const rule = rerunExceptQueryParam('trade');

  it('skips the resolvers when only the named parameter is added, changed or removed', () => {
    expect(rule(snap({}), snap({ trade: 't1' }))).toBe(false);
    expect(rule(snap({ trade: 't1' }), snap({ trade: 't2' }))).toBe(false);
    expect(rule(snap({ trade: 't1', status: 'ACTIVE' }), snap({ status: 'ACTIVE' }))).toBe(false);
  });

  it('re-runs an identical URL, as "always" did (the SSE refresh re-navigates the same URL)', () => {
    expect(rule(snap({}), snap({}))).toBe(true);
    expect(rule(snap({ trade: 't1' }), snap({ trade: 't1' }))).toBe(true);
  });

  it('re-runs when anything besides the named parameter changes', () => {
    expect(rule(snap({ scope: 'today' }), snap({ scope: 'all' }))).toBe(true);
    expect(rule(snap({ trade: 't1' }), snap({ trade: 't2', scope: 'all' }))).toBe(true);
    expect(rule(snap({}, { id: 'a' }), snap({ trade: 't1' }, { id: 'b' }))).toBe(true);
  });

  it('compares multi-valued parameters by value', () => {
    expect(rule(snap({ tag: ['a', 'b'] }), snap({ tag: ['a', 'b'], trade: 't1' }))).toBe(false);
    expect(rule(snap({ tag: ['a', 'b'] }), snap({ tag: ['a'], trade: 't1' }))).toBe(true);
  });
});
