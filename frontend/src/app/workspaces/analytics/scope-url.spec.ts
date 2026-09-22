import { convertToParamMap } from '@angular/router';
import { describe, expect, it } from 'vitest';

import { DEFAULT_SCOPE } from '../../stores/analytics.store';
import { scopeFromParams, scopeToQueryParams } from './scope-url';

describe('scope-url', () => {
  it('reads every field, defaulting the unset ones', () => {
    const got = scopeFromParams(convertToParamMap({ tab: 'execution', from: '2026-08-01', ledger: 'weak', unit: 'money' }));
    expect(got.tab).toBe('execution');
    expect(got.scope).toEqual({ ...DEFAULT_SCOPE, from: '2026-08-01', ledger: 'weak' });
    expect(got.unit).toBe('money');
  });

  it('maps legacy tabs and rejects nonsense', () => {
    expect(scopeFromParams(convertToParamMap({ tab: 'performance' })).tab).toBe('overview');
    expect(scopeFromParams(convertToParamMap({ tab: 'calibration' })).tab).toBe('edge');
    expect(scopeFromParams(convertToParamMap({ tab: 'nope', ledger: 'nope', unit: 'nope' })))
      .toEqual({ tab: 'overview', scope: DEFAULT_SCOPE, unit: 'r' });
  });

  it('writes defaults as null so one state has one URL', () => {
    expect(scopeToQueryParams('overview', DEFAULT_SCOPE, 'r'))
      .toEqual({ tab: null, from: null, to: null, ledger: null, strategy: null, horizon: null, direction: null, unit: null });
    expect(scopeToQueryParams('edge', { ...DEFAULT_SCOPE, strategy: 'MACD' }, 'pct'))
      .toEqual({ tab: 'edge', from: null, to: null, ledger: null, strategy: 'MACD', horizon: null, direction: null, unit: 'pct' });
  });

  it('refuses a malformed date rather than sending it to the server', () => {
    // An unparseable `from=` would 400 the first request of every panel on
    // the page; falling back to unbounded degrades to all-time instead.
    expect(scopeFromParams(convertToParamMap({ from: '01-08-2026', to: 'yesterday' })).scope)
      .toEqual(DEFAULT_SCOPE);
  });
});
