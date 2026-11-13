import { Injectable, Injector, Signal, effect, inject, signal, untracked } from '@angular/core';

import { ApiClient } from '../api/api-client';
import { EventStream } from '../api/event-stream';
import { FeedPost } from '../api/models';
import { VoicePrefs } from './voice-prefs';
import { SPEECH, VoiceSpeaker } from './voice-speaker';

/** At most this many headlines per fetch; the rest become "and N more". */
export const RECONNECT_CAP = 5;
/** The server's maximum page; a full page means there may be more. */
export const FEED_PAGE_LIMIT = 50;

export const moreLine = (n: number): string => `and ${n} more`;

/**
 * Turns `feed` events into speech (spec v227 §3).
 *
 * The bot records every accepted simple-channel post in `feed_posts`; its
 * NOTIFY trigger raises `feed` on the event stream. Each bump fetches the
 * rows after the last id this tab has seen -- one fetch at a time, paging
 * while a page is full -- drops the kinds the partner silenced and hands the
 * newest five headlines to `VoiceSpeaker`. The cursor starts at the latest id
 * when the page loads, so a post made while no tab was open is never spoken.
 *
 * A resync bumps `feed` like every other event; the fetch then simply finds
 * nothing after the cursor.
 */
@Injectable({ providedIn: 'root' })
export class VoiceNotifier {
  private readonly api = inject(ApiClient);
  private readonly events = inject(EventStream);
  private readonly prefs = inject(VoicePrefs);
  private readonly speaker = inject(VoiceSpeaker);
  private readonly speech = inject(SPEECH);
  private readonly injector = inject(Injector);

  private readonly cursor = signal<number | null>(null);
  /** The last post id this tab has dealt with; null before the first answer. */
  readonly lastId: Signal<number | null> = this.cursor.asReadonly();

  private started = false;
  private fetching = false;
  private pending = false;
  private seen = 0;

  /** Called once by the shell; later calls do nothing. */
  start(): void {
    if (this.started || !this.speech) return;
    this.started = true;
    const feed = this.events.changes('feed');
    this.seen = untracked(feed);
    effect(() => {
      const count = feed();
      untracked(() => this.onFeed(count));
    }, { injector: this.injector });
    this.fetch();
  }

  private onFeed(count: number): void {
    if (count === this.seen) return;
    this.seen = count;
    this.fetch();
  }

  private fetch(): void {
    if (this.fetching) {
      this.pending = true;
      return;
    }
    this.fetching = true;
    this.page(this.cursor(), []);
  }

  private page(after: number | null, collected: FeedPost[]): void {
    this.api.feedPosts(after, FEED_PAGE_LIMIT).subscribe({
      next: (page) => {
        const items = [...collected, ...page.items];
        const last = page.items.at(-1)?.id ?? null;
        if (last !== null && page.items.length >= FEED_PAGE_LIMIT) {
          this.page(last, items);
          return;
        }
        this.cursor.set(last ?? page.latest_id);
        this.speak(items);
        this.done();
      },
      error: () => this.done(),
    });
  }

  private done(): void {
    this.fetching = false;
    if (!this.pending) return;
    this.pending = false;
    this.fetch();
  }

  private speak(items: FeedPost[]): void {
    if (!this.prefs.value().enabled) return;
    const kept = items.filter((item) => this.prefs.isKindOn(item.kind, item.family)).map((item) => item.headline);
    if (kept.length === 0) return;
    const lines = kept.slice(-RECONNECT_CAP);
    const skipped = kept.length - lines.length;
    this.speaker.say(skipped > 0 ? [...lines, moreLine(skipped)] : lines);
  }
}
