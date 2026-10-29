import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { Component, provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it } from 'vitest';

import { PHONE_TABS } from './nav';
import { PhoneTabBar } from './phone-tab-bar';

@Component({ template: '' })
class Blank {}

describe('PhoneTabBar (v195 Phase 3)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideZonelessChangeDetection(), provideRouter([{ path: '**', component: Blank }])],
    });
  });

  async function mount(url: string, moreOpen = false) {
    await TestBed.inject(Router).navigateByUrl(url);
    const fixture = TestBed.createComponent(PhoneTabBar);
    fixture.componentRef.setInput('moreOpen', moreOpen);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    return { fixture, el: fixture.nativeElement as HTMLElement };
  }

  const current = (el: HTMLElement) =>
    [...el.querySelectorAll('a.tab[aria-current="page"]')].map((a) => a.querySelector('.tab-label')!.textContent!.trim());

  it('holds Dashboard, Watchlist, Trades, Risk and More, in that order', async () => {
    const { el } = await mount('/dashboard');
    expect(el.querySelector('nav')!.getAttribute('aria-label')).toBe('Main pages');
    expect([...el.querySelectorAll('.tab .tab-label')].map((n) => n.textContent!.trim()))
      .toEqual(['Dashboard', 'Watchlist', 'Trades', 'Risk', 'More']);
    expect([...el.querySelectorAll('a.tab')].map((a) => a.getAttribute('href')))
      .toEqual(PHONE_TABS.map((tab) => tab.path));
  });

  it('marks the current tab, and the list tab for its detail pages', async () => {
    expect(current((await mount('/risk')).el)).toEqual(['Risk']);
    expect(current((await mount('/plans/7')).el)).toEqual(['Trades']);
    expect(current((await mount('/watchlist/NVDA')).el)).toEqual(['Watchlist']);
  });

  it('lights More for a page the bar does not hold', async () => {
    const { el } = await mount('/calendar');
    expect(current(el)).toEqual([]);
    expect(el.querySelector('button.tab.more')!.classList).toContain('active');
  });

  it('asks for the More sheet and reports it open', async () => {
    const { fixture, el } = await mount('/dashboard');
    let asked = 0;
    fixture.componentInstance.moreRequested.subscribe(() => (asked += 1));
    const more = el.querySelector<HTMLButtonElement>('button.tab.more')!;
    expect(more.getAttribute('aria-haspopup')).toBe('dialog');
    expect(more.getAttribute('aria-expanded')).toBe('false');
    expect(more.classList).not.toContain('active');
    more.click();
    expect(asked).toBe(1);
    fixture.componentRef.setInput('moreOpen', true);
    fixture.detectChanges();
    expect(more.getAttribute('aria-expanded')).toBe('true');
    expect(more.classList).toContain('active');
  });

  it('keeps every glyph out of the accessible name', async () => {
    const { el } = await mount('/dashboard');
    const icons = [...el.querySelectorAll('sb-icon')];
    expect(icons).toHaveLength(5);
    for (const icon of icons) {
      expect(icon.parentElement!.matches('.glyph[aria-hidden="true"]')).toBe(true);
    }
  });

  it('sits on the bottom edge at 56px plus the safe-area inset, under the toasts', () => {
    const source = readFileSync(join(process.cwd(), 'src/app/shell/phone-tab-bar.ts'), 'utf8');
    expect(source).toContain('height: calc(56px + env(safe-area-inset-bottom));');
    expect(source).toContain('padding-bottom: env(safe-area-inset-bottom);');
    expect(source).toMatch(/:host \{[^}]*position: fixed;[^}]*z-index: 8;/s);
  });
});
