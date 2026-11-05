import { EffectRef, effect, inject, untracked } from '@angular/core';

import { MarketMeta, SnapshotUpdate } from '../api/models';
import { LiveValuesStore } from './live-values.store';

export function followSnapshot(
  key: () => string | null, loadedAt: () => string | null, reload: () => void,
): EffectRef {
  const live = inject(LiveValuesStore);
  const seen = new Set<string>();
  return effect(() => {
    const k = key();
    if (!k) return;
    const at = live.snapshot(k)()?.computed_at;
    const loaded = loadedAt();
    if (!at) return;
    const version = `${k}@${at}`;
    if (seen.has(version) || (loaded !== null && !(Date.parse(at) > Date.parse(loaded)))) return;
    seen.add(version);
    untracked(reload);
  });
}

export function snapshotMeta(
  meta: MarketMeta | null | undefined, live: SnapshotUpdate | null,
): MarketMeta | null {
  if (!meta) return null;
  if (live === null) return meta;
  return { ...meta, refreshing: meta.refreshing || live.refreshing, error: meta.error ?? live.error };
}
