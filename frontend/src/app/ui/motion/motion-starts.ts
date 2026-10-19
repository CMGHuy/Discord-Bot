import { Injectable } from '@angular/core';

export type MotionStartKind = 'entrance' | 'count-first' | 'count-change' | 'draw-in' | 'flash';

export interface MotionStart {
  kind: MotionStartKind;
  key: string;
}

/** Enough for any gate; small enough that a page left open all day stays flat. */
const CAP = 200;

/**
 * Every animation START, recorded by the route host, count-up, draw-in and
 * flash (spec v168 §4). The no-replay gate reads it, because jsdom has no
 * getAnimations() and never fires animationstart. In the browser it is a
 * small ring of the latest starts and nothing reads it.
 */
@Injectable({ providedIn: 'root' })
export class MotionStarts {
  private readonly log: MotionStart[] = [];

  record(kind: MotionStartKind, key: string): void {
    this.log.push({ kind, key });
    if (this.log.length > CAP) this.log.shift();
  }

  entries(): readonly MotionStart[] {
    return [...this.log];
  }

  count(kind: MotionStartKind): number {
    return this.log.filter((start) => start.kind === kind).length;
  }

  clear(): void {
    this.log.length = 0;
  }
}
