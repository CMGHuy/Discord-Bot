import { signal } from '@angular/core';

import { EquityBasis, EquityCandlesResponse, EquityTimeframe } from '../api/models';

/**
 * A stand-in for `EquityCandlesStore` in component specs (v172): the same
 * signal and method names, no HTTP, no EventStream, no preferences. `calls`
 * records what the component asked for.
 */
export function equityCandlesStoreStub(data: EquityCandlesResponse | null = null) {
  const tf = signal<EquityTimeframe>(data?.tf ?? '1D');
  const basis = signal<EquityBasis>(data?.basis ?? 'mtm');
  const calls = { load: 0, tf: [] as EquityTimeframe[], basis: [] as EquityBasis[] };
  return {
    tf: tf.asReadonly(),
    basis: basis.asReadonly(),
    data: signal<EquityCandlesResponse | null>(data),
    loading: signal(false),
    error: signal<string | null>(null),
    calls,
    load: (): void => {
      calls.load += 1;
    },
    setTimeframe: (value: EquityTimeframe): void => {
      calls.tf.push(value);
      tf.set(value);
    },
    setBasis: (value: EquityBasis): void => {
      calls.basis.push(value);
      basis.set(value);
    },
  };
}

export type EquityCandlesStoreStub = ReturnType<typeof equityCandlesStoreStub>;
