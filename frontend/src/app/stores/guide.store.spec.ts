import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { describe, expect, it } from 'vitest';

import { authInterceptor, errorInterceptor, loadingInterceptor } from '../api/interceptors';
import { GuideChapter, GuideIndex } from '../api/models';
import { GuideStore } from './guide.store';

/* What earns tests here: the index is fetched once per visit however often
 * the resolver runs; a chapter body is fetched once, a 404 reads as a
 * missing chapter (not a broken page) and any other failure can be retried. */

const INDEX: GuideIndex = {
  chapters: [
    { slug: 'what-it-is', title: 'What the bot is (and isn’t)', order: 1, reviewed_for: '2.19.2',
      headings: [{ level: 2, text: 'The notice', anchor: 'the-notice' }] },
    { slug: 'glossary', title: 'Glossary', order: 12, reviewed_for: '2.19.2', headings: [] },
  ],
};

const CHAPTER: GuideChapter = {
  slug: 'glossary', title: 'Glossary', reviewed_for: '2.19.2', markdown: '> **In plain words** terms.',
};

function seed() {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideHttpClient(withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor])),
      provideHttpClientTesting(),
      GuideStore,
    ],
  });
  return { http: TestBed.inject(HttpTestingController), store: TestBed.inject(GuideStore) };
}

describe('GuideStore: the index', () => {
  it('starts idle with nothing loaded', () => {
    const { store } = seed();
    expect(store.status()).toBe('idle');
    expect(store.chapters()).toEqual([]);
    expect(store.firstSlug()).toBeNull();
  });

  it('fetches the index once and exposes the first chapter', async () => {
    const { http, store } = seed();
    const first = store.ensureLoaded();
    const second = store.ensureLoaded();
    http.expectOne('/api/v1/guide').flush(INDEX);
    await Promise.all([first, second]);
    expect(store.status()).toBe('ready');
    expect(store.chapters().map((c) => c.slug)).toEqual(['what-it-is', 'glossary']);
    expect(store.firstSlug()).toBe('what-it-is');
    await store.ensureLoaded();
    http.expectNone('/api/v1/guide');
    http.verify();
  });

  it('reports an unreachable admin in words and loads again on the next call', async () => {
    const { http, store } = seed();
    const pending = store.ensureLoaded();
    http.expectOne('/api/v1/guide').error(new ProgressEvent('error'), { status: 0 });
    await pending;
    expect(store.status()).toBe('error');
    expect(store.error()).toBe('The admin is not responding — the guide is unavailable.');
    const retry = store.ensureLoaded();
    http.expectOne('/api/v1/guide').flush(INDEX);
    await retry;
    expect(store.status()).toBe('ready');
    expect(store.error()).toBeNull();
  });

  it('shows the server message for a placeholder failure', async () => {
    const { http, store } = seed();
    const pending = store.ensureLoaded();
    http.expectOne('/api/v1/guide').flush(
      { error: { code: 'guide_placeholder', message: 'Unknown guide placeholder: nope' } },
      { status: 500, statusText: 'Server Error' },
    );
    await pending;
    expect(store.error()).toBe('Unknown guide placeholder: nope');
  });

  it('reads an empty guide as ready with no chapters', async () => {
    const { http, store } = seed();
    const pending = store.ensureLoaded();
    http.expectOne('/api/v1/guide').flush({ chapters: [] });
    await pending;
    expect(store.status()).toBe('ready');
    expect(store.firstSlug()).toBeNull();
  });
});

describe('GuideStore: chapter bodies', () => {
  it('fetches a body once and keeps it', () => {
    const { http, store } = seed();
    store.loadChapter('glossary');
    expect(store.chapterStatus()['glossary']).toBe('loading');
    store.loadChapter('glossary');
    http.expectOne('/api/v1/guide/glossary').flush(CHAPTER);
    expect(store.chapterStatus()['glossary']).toBe('ready');
    expect(store.bodies()['glossary']).toEqual(CHAPTER);
    store.loadChapter('glossary');
    http.expectNone('/api/v1/guide/glossary');
    http.verify();
  });

  it('marks an unknown slug missing', () => {
    const { http, store } = seed();
    store.loadChapter('nope');
    http.expectOne('/api/v1/guide/nope').flush(
      { error: { code: 'not_found', message: 'No guide chapter nope' } },
      { status: 404, statusText: 'Not Found' },
    );
    expect(store.chapterStatus()['nope']).toBe('missing');
    expect(store.bodies()['nope']).toBeUndefined();
  });

  it('marks any other failure as an error that may be retried', () => {
    const { http, store } = seed();
    store.loadChapter('glossary');
    http.expectOne('/api/v1/guide/glossary').flush(
      { error: { code: 'guide_placeholder', message: 'Unknown guide placeholder: x' } },
      { status: 500, statusText: 'Server Error' },
    );
    expect(store.chapterStatus()['glossary']).toBe('error');
    store.loadChapter('glossary');
    http.expectOne('/api/v1/guide/glossary').flush(CHAPTER);
    expect(store.chapterStatus()['glossary']).toBe('ready');
  });

  it('encodes the slug into the URL', () => {
    const { http, store } = seed();
    store.loadChapter('a b');
    http.expectOne('/api/v1/guide/a%20b').flush({ ...CHAPTER, slug: 'a b' });
    expect(store.chapterStatus()['a b']).toBe('ready');
  });
});
