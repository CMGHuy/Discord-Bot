import { computed, inject } from '@angular/core';
import { patchState, signalStore, withComputed, withMethods, withState } from '@ngrx/signals';
import { firstValueFrom } from 'rxjs';

import { ApiClient } from '../api/api-client';
import { ApiError } from '../api/api-error';
import { GuideChapter, GuideChapterSummary } from '../api/models';
import { routeRequest } from '../routing/route-request';

export type GuideStatus = 'idle' | 'loading' | 'ready' | 'error';
export type GuideChapterStatus = 'loading' | 'ready' | 'missing' | 'error';

interface GuideSlice {
  chapters: GuideChapterSummary[];
  bodies: Record<string, GuideChapter>;
  status: GuideStatus;
  error: string | null;
  chapterStatus: Record<string, GuideChapterStatus>;
}

const UNAVAILABLE = 'The admin is not responding — the guide is unavailable.';

/**
 * The Guide page's data (v235): the chapter index once per visit, and each
 * chapter body the first time it is opened.
 *
 * Chapters change only with a deploy, so nothing refetches on an event. The
 * index carries every heading, so the table of contents and heading search
 * work before any body is fetched; bodies stay in `bodies` so search can
 * cover the text of every chapter the reader has opened.
 */
export const GuideStore = signalStore(
  withState<GuideSlice>({
    chapters: [], bodies: {}, status: 'idle', error: null, chapterStatus: {},
  }),
  withComputed(({ chapters }) => ({
    /** The chapter `/insights/guide` opens on: the first in reading order. */
    firstSlug: computed<string | null>(() => chapters()[0]?.slug ?? null),
  })),
  withMethods((store, api = inject(ApiClient)) => {
    let pending: Promise<void> | null = null;
    const setChapter = (slug: string, status: GuideChapterStatus) =>
      patchState(store, { chapterStatus: { ...store.chapterStatus(), [slug]: status } });
    const index = () => routeRequest(api.guide(), {
      start: () => patchState(store, { status: 'loading' }),
      next: ({ chapters }) => patchState(store, { chapters, status: 'ready', error: null }),
      error: (error) => patchState(store, {
        status: 'error',
        error: error.code === 'unavailable' ? UNAVAILABLE : error.message,
      }),
    });
    return {
      /** For the route resolver: resolves once the index has landed or
       *  failed; a later call after a failure fetches again. An auth
       *  failure rejects, so `startRoute` can expire the session. */
      ensureLoaded(): Promise<void> {
        if (store.status() === 'ready') return Promise.resolve();
        pending ??= firstValueFrom(index(), { defaultValue: undefined })
          .finally(() => { pending = null; });
        return pending;
      },
      loadChapter(slug: string): void {
        const now = store.chapterStatus()[slug];
        if (now === 'loading' || now === 'ready') return;
        setChapter(slug, 'loading');
        api.guideChapter(slug).subscribe({
          next: (chapter) => {
            patchState(store, { bodies: { ...store.bodies(), [slug]: chapter } });
            setChapter(slug, 'ready');
          },
          error: (error: unknown) => setChapter(
            slug, error instanceof ApiError && error.code === 'not_found' ? 'missing' : 'error'),
        });
      },
    };
  }),
);
