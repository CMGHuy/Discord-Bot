import { Inject, Injectable, InjectionToken, signal, Signal } from '@angular/core';

export type ChartLayer = 'macd' | 'rsi' | 'keltner' | 'volumeProfile' | 'plan';

/**
 * A key-value store interface for chart preferences.
 *
 * Implemented by Map (for tests) and localStorage via adapter (for production).
 * localStorage has getItem/setItem; this interface uses get/set.
 */
interface ChartPrefsStore {
  get(key: string): string | undefined;
  set(key: string, value: string): void;
}

/**
 * Adapter to wrap localStorage into a ChartPrefsStore interface.
 */
function localStorageAdapter(): ChartPrefsStore {
  return {
    get(key: string): string | undefined {
      const value = localStorage.getItem(key);
      return value ?? undefined;
    },
    set(key: string, value: string): void {
      localStorage.setItem(key, value);
    },
  };
}

/**
 * Injection token for the chart preferences store.
 * Provides localStorageAdapter by default, overridable for tests.
 */
export const CHART_PREFS_STORE = new InjectionToken<ChartPrefsStore>(
  'CHART_PREFS_STORE',
  { providedIn: 'root', factory: localStorageAdapter },
);

const DEFAULT_LAYERS: Record<ChartLayer, boolean> = {
  macd: true,
  rsi: true,
  keltner: true,
  volumeProfile: true,
  plan: true,
};

const STORAGE_KEY = 'sb.chart.layers';

/**
 * Persists user-toggled chart indicator visibility across page reloads.
 *
 * A stored value is a *hint*, validated against the baseline: for each known
 * layer, only accept true or false; anything else (wrong type, missing key,
 * unknown key) falls back to that layer's default (visible). Unknown keys are
 * dropped entirely rather than carried forward.
 */
@Injectable({ providedIn: 'root' })
export class ChartPrefs {
  readonly visible: Signal<Record<ChartLayer, boolean>>;
  private readonly visibilitySignal;
  private readonly store: ChartPrefsStore;

  constructor(@Inject(CHART_PREFS_STORE) store: ChartPrefsStore = localStorageAdapter()) {
    this.store = store;
    const loaded = this.loadInitial();
    this.visibilitySignal = signal(loaded);
    this.visible = this.visibilitySignal.asReadonly();
  }

  private loadInitial(): Record<ChartLayer, boolean> {
    const stored = this.store.get(STORAGE_KEY);
    if (!stored) {
      return { ...DEFAULT_LAYERS };
    }

    try {
      const parsed = JSON.parse(stored);
      if (typeof parsed !== 'object' || parsed === null) {
        return { ...DEFAULT_LAYERS };
      }

      // Validate each layer individually: only accept true or false,
      // default to visible if type is wrong or key is missing.
      // Drop unknown keys entirely.
      const result: Record<ChartLayer, boolean> = { ...DEFAULT_LAYERS };
      for (const layer of Object.keys(DEFAULT_LAYERS) as ChartLayer[]) {
        const value = parsed[layer];
        if (typeof value === 'boolean') {
          result[layer] = value;
        }
        // else: keep the default from DEFAULT_LAYERS
      }
      return result;
    } catch {
      // Corrupt JSON - ignore and use defaults
    }

    return { ...DEFAULT_LAYERS };
  }

  toggle(layer: ChartLayer): void {
    this.visibilitySignal.update((current) => {
      const next = { ...current, [layer]: !current[layer] };
      this.store.set(STORAGE_KEY, JSON.stringify(next));
      return next;
    });
  }
}
