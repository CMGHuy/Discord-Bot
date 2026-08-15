import { signal, Signal } from '@angular/core';

export type ChartLayer = 'macd' | 'rsi' | 'keltner' | 'volumeProfile' | 'plan';

interface Storage {
  get(key: string): string | undefined;
  set(key: string, value: string): void;
}

const DEFAULT_LAYERS: Record<ChartLayer, boolean> = {
  macd: true,
  rsi: true,
  keltner: true,
  volumeProfile: true,
  plan: true,
};

const STORAGE_KEY = 'sb.chart.layers';

export class ChartPrefs {
  readonly visible: Signal<Record<ChartLayer, boolean>>;
  private readonly visibilitySignal;
  private readonly storage: Storage;

  constructor(storage: Storage) {
    this.storage = storage;
    const loaded = this.loadInitial();
    this.visibilitySignal = signal(loaded);
    this.visible = this.visibilitySignal.asReadonly();
  }

  private loadInitial(): Record<ChartLayer, boolean> {
    const stored = this.storage.get(STORAGE_KEY);
    if (!stored) {
      return { ...DEFAULT_LAYERS };
    }

    try {
      const parsed = JSON.parse(stored);
      if (typeof parsed === 'object' && parsed !== null) {
        return { ...DEFAULT_LAYERS, ...parsed };
      }
    } catch {
      // Corrupt JSON - ignore and use defaults
    }

    return { ...DEFAULT_LAYERS };
  }

  toggle(layer: ChartLayer): void {
    this.visibilitySignal.update((current) => {
      const next = { ...current, [layer]: !current[layer] };
      this.storage.set(STORAGE_KEY, JSON.stringify(next));
      return next;
    });
  }
}
