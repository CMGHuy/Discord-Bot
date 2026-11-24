import { Component, provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { patchState } from '@ngrx/signals';
import { unprotected } from '@ngrx/signals/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { MoreSheet, morePageGroups } from './more-sheet';
import { DEFAULT_PHONE_TAB_PATHS, NAV_ENTRIES, phoneTabsFor } from './nav';
import { TAB_BAR_PREF_KEY, TAB_BAR_STORAGE, TabBarPrefs } from './tab-bar-prefs';
import { SessionStore } from '../stores/session.store';

const DEFAULT_TABS = phoneTabsFor(DEFAULT_PHONE_TAB_PATHS);

@Component({ template: '' })
class Blank {}

describe('morePageGroups (v202 §3)', () => {
  const shape = (groups: ReturnType<typeof morePageGroups>) =>
    groups.map((group) => [group.id, group.label, group.links.map((link) => [link.label, link.path])]);

  it('lists the destinations the tab bar does not hold, each with its sections, in rail order', () => {
    expect(shape(morePageGroups(NAV_ENTRIES, DEFAULT_TABS))).toEqual([
      ['more-risk', 'Risk', [['Risk', '/risk']]],
      ['more-insights', 'Insights', [['Analytics', '/insights/analytics'], ['Research', '/insights/research'], ['Reports', '/insights/reports'], ['Guide', '/insights/guide']]],
      ['more-system', 'System', [['Health', '/system'], ['Versions', '/system/versions']]],
    ]);
  });

  it('lists no destination the tab bar holds', () => {
    const ids = morePageGroups(NAV_ENTRIES, DEFAULT_TABS).map((group) => group.id);
    for (const id of ['more-dashboard', 'more-watchlist', 'more-trades', 'more-calendar']) expect(ids).not.toContain(id);
  });

  it('keeps every destination when no tab is given, a single page linking to itself', () => {
    const groups = morePageGroups(NAV_ENTRIES, []);
    expect(groups).toHaveLength(7);
    expect(shape(groups)[0]).toEqual(['more-dashboard', 'Dashboard', [['Dashboard', '/dashboard']]]);
    expect(shape(groups)[2]).toEqual(['more-trades', 'Trades', [['Trades', '/trades']]]);
    expect(shape(groups)[3]).toEqual(['more-calendar', 'Calendar', [['Calendar', '/calendar']]]);
  });

  it('follows the tab list it is given', () => {
    const tabs = phoneTabsFor(['/dashboard', '/risk']);
    expect(morePageGroups(NAV_ENTRIES, tabs).map((group) => group.label))
      .toEqual(['Watchlist', 'Trades', 'Calendar', 'Insights', 'System']);
  });

  it('is empty for an empty model', () => {
    expect(morePageGroups([], [])).toEqual([]);
  });
});

describe('MoreSheet (v195 Phase 3)', () => {
  let fixture: ComponentFixture<MoreSheet>;
  let el: HTMLElement;
  let closed: number;
  let searched: number;
  let stored: Map<string, string>;

  /** An in-memory ui.tabbar, read through the closure so a test may reseed it. */
  const storageProvider = () => ({
    provide: TAB_BAR_STORAGE,
    useValue: { get: (key: string) => stored.get(key) ?? null, set: (key: string, value: string) => void stored.set(key, value) },
  });

  function configure(role: 'admin' | 'viewer'): void {
    TestBed.configureTestingModule({
      providers: [provideZonelessChangeDetection(), provideRouter([{ path: '**', component: Blank }]), storageProvider()],
    });
    patchState(unprotected(TestBed.inject(SessionStore)), { status: 'authenticated', username: role, role });
  }

  function create(): void {
    fixture = TestBed.createComponent(MoreSheet);
    el = fixture.nativeElement as HTMLElement;
    closed = 0;
    searched = 0;
    fixture.componentInstance.closed.subscribe(() => (closed += 1));
    fixture.componentInstance.searchRequested.subscribe(() => (searched += 1));
    fixture.detectChanges();
  }

  beforeEach(() => {
    stored = new Map<string, string>();
    configure('admin');
    create();
  });

  function open(): void {
    fixture.componentRef.setInput('open', true);
    fixture.detectChanges();
  }

  const groupLabels = () => [...el.querySelectorAll('.group-label')].map((n) => n.textContent!.trim());

  it('lists what the partner took off the bar, and drops what they put on it (v240 §6)', () => {
    const prefs = TestBed.inject(TabBarPrefs);
    prefs.remove('/watchlist');
    prefs.add('/risk');
    open();
    expect(groupLabels()).toEqual(['Watchlist', 'Insights', 'System']);
    prefs.remove('/risk');
    fixture.detectChanges();
    expect(groupLabels()).toEqual(['Watchlist', 'Risk', 'Insights', 'System']);
  });

  it('reads the stored bar, ignoring a System tab for a viewer', () => {
    TestBed.resetTestingModule();
    stored = new Map([[TAB_BAR_PREF_KEY, '["/dashboard","/system","/insights"]']]);
    configure('viewer');
    create();
    open();
    expect(groupLabels()).toEqual(['Watchlist', 'Trades', 'Calendar', 'Risk']);
  });

  const dialog = () => el.querySelector<HTMLElement>('[role=dialog]');

  it('lists only Risk and Insights for a viewer (v207)', () => {
    patchState(unprotected(TestBed.inject(SessionStore)), { role: 'viewer' });
    open();
    expect([...el.querySelectorAll('.group-label')].map((n) => n.textContent!.trim())).toEqual(['Risk', 'Insights']);
    expect([...el.querySelectorAll('a.page')].map((a) => a.getAttribute('href')))
      .toEqual(['/risk', '/insights/analytics', '/insights/research', '/insights/reports', '/insights/guide']);
  });

  it('renders nothing while closed, and ignores Escape then', () => {
    expect(dialog()).toBeNull();
    expect(el.querySelector('.scrim')).toBeNull();
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    expect(closed).toBe(0);
  });

  it('opens as a labelled modal dialog with focus on the search field', () => {
    open();
    expect(dialog()!.getAttribute('aria-modal')).toBe('true');
    expect(dialog()!.getAttribute('aria-label')).toBe('More');
    expect(dialog()!.classList).toContain('elev-overlay');
    expect(document.activeElement).toBe(el.querySelector('button.search'));
    expect(el.querySelector('button.search')!.textContent!.trim()).toBe('Search or jump…');
  });

  it('lists the remaining destinations under their names, linking to each section', () => {
    open();
    expect([...el.querySelectorAll('.group-label')].map((n) => n.textContent!.trim()))
      .toEqual(['Risk', 'Insights', 'System']);
    expect([...el.querySelectorAll('a.page')].map((a) => [a.textContent!.trim(), a.getAttribute('href')])).toEqual([
      ['Risk', '/risk'],
      ['Analytics', '/insights/analytics'], ['Research', '/insights/research'], ['Reports', '/insights/reports'], ['Guide', '/insights/guide'],
      ['Health', '/system'], ['Versions', '/system/versions'],
    ]);
    for (const list of el.querySelectorAll('ul.pages')) {
      expect(el.querySelector(`#${list.getAttribute('aria-labelledby')}`)).not.toBeNull();
    }
  });

  it('draws no glyph in a section link', () => {
    open();
    expect(el.querySelectorAll('a.page sb-icon')).toHaveLength(0);
  });

  it('closes on Escape, on the scrim, on Close and on choosing a page', () => {
    open();
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    el.querySelector<HTMLElement>('.scrim')!.click();
    el.querySelector<HTMLButtonElement>('button.close')!.click();
    el.querySelector<HTMLAnchorElement>('a.page')!.click();
    expect(closed).toBe(4);
  });

  it('asks for search from its search field', () => {
    open();
    el.querySelector<HTMLButtonElement>('button.search')!.click();
    expect(searched).toBe(1);
  });
});
