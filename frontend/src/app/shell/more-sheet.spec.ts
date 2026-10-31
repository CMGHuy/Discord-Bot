import { Component, provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it } from 'vitest';

import { MoreSheet, morePageGroups } from './more-sheet';
import { NAV_GROUPS } from './nav';

@Component({ template: '' })
class Blank {}

describe('morePageGroups (v195 Phase 3)', () => {
  it('keeps the pages the tab bar does not hold, grouped and in rail order', () => {
    expect(morePageGroups().map((group) => [group.label, group.entries.map((entry) => entry.label)])).toEqual([
      ['Review', ['Calendar', 'Cancels']],
      ['Insights', ['Analytics', 'Research', 'Reports']],
      ['System', ['System', 'Versions']],
    ]);
  });

  it('drops a group whose every page is already a tab', () => {
    expect(morePageGroups().some((group) => group.id === 'nav-monitor')).toBe(false);
  });

  it('keeps every group when no tab is given', () => {
    expect(morePageGroups(NAV_GROUPS, [])).toHaveLength(4);
  });
});

describe('MoreSheet (v195 Phase 3)', () => {
  let fixture: ComponentFixture<MoreSheet>;
  let el: HTMLElement;
  let closed: number;
  let searched: number;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideZonelessChangeDetection(), provideRouter([{ path: '**', component: Blank }])],
    });
    fixture = TestBed.createComponent(MoreSheet);
    el = fixture.nativeElement as HTMLElement;
    closed = 0;
    searched = 0;
    fixture.componentInstance.closed.subscribe(() => (closed += 1));
    fixture.componentInstance.searchRequested.subscribe(() => (searched += 1));
    fixture.detectChanges();
  });

  function open(): void {
    fixture.componentRef.setInput('open', true);
    fixture.detectChanges();
  }

  const dialog = () => el.querySelector<HTMLElement>('[role=dialog]');

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

  it('lists the remaining pages under their group names, linking to each', () => {
    open();
    expect([...el.querySelectorAll('.group-label')].map((n) => n.textContent!.trim()))
      .toEqual(['Review', 'Insights', 'System']);
    expect([...el.querySelectorAll('a.page')].map((a) => [a.textContent!.trim(), a.getAttribute('href')])).toEqual([
      ['Calendar', '/calendar'], ['Cancels', '/cancels'],
      ['Analytics', '/analytics'], ['Research', '/research'], ['Reports', '/reports'],
      ['System', '/system'], ['Versions', '/versions'],
    ]);
    for (const list of el.querySelectorAll('ul.pages')) {
      expect(el.querySelector(`#${list.getAttribute('aria-labelledby')}`)).not.toBeNull();
    }
    for (const icon of el.querySelectorAll('a.page sb-icon')) {
      expect(icon.parentElement!.matches('.glyph[aria-hidden="true"]')).toBe(true);
    }
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
