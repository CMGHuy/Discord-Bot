import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { Component, provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it } from 'vitest';

import { allSources } from '../ui/testing/all-sources';
import { NAV_ENTRIES, NavEntry, NavSection } from './nav';
import { SectionTabs } from './section-tabs';

@Component({ template: '' })
class Blank {}

const SOURCE = readFileSync(join(process.cwd(), 'src/app/shell/section-tabs.ts'), 'utf8');
const entry = (path: string) => NAV_ENTRIES.find((candidate) => candidate.path === path)!;
const section = (path: string) => NAV_ENTRIES.flatMap((e) => e.sections ?? []).find((s) => s.path === path)!;

describe('SectionTabs (sb-section-tabs, v202 §1)', () => {
  let fixture: ComponentFixture<SectionTabs>;
  const el = () => fixture.nativeElement as HTMLElement;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideZonelessChangeDetection(), provideRouter([{ path: '**', component: Blank }])],
    });
    fixture = TestBed.createComponent(SectionTabs);
  });

  function render(navEntry: NavEntry | null, active: NavSection | null): void {
    fixture.componentRef.setInput('entry', navEntry);
    fixture.componentRef.setInput('active', active);
    fixture.detectChanges();
  }

  const tabs = () => [...el().querySelectorAll('a.segment')].map((a) => [a.textContent!.trim(), a.getAttribute('href')]);

  it('renders nothing off the nav and on a single page', () => {
    render(null, null);
    expect(el().querySelector('nav')).toBeNull();
    render(entry('/risk'), null);
    expect(el().querySelector('nav')).toBeNull();
  });

  it("draws a destination's sections as links, in order, in a labelled nav", () => {
    render(entry('/trades'), section('/trades/calendar'));
    expect(el().querySelector('nav')!.getAttribute('aria-label')).toBe('Trades sections');
    expect(tabs()).toEqual([['Book', '/trades'], ['Calendar', '/trades/calendar']]);
  });

  it('marks only the active section as the current page', () => {
    render(entry('/insights'), section('/insights/research'));
    const current = [...el().querySelectorAll('a[aria-current="page"]')];
    expect(current.map((a) => a.textContent!.trim())).toEqual(['Research']);
    expect(current[0].classList).toContain('current');
    expect(el().querySelectorAll('a.segment.current')).toHaveLength(1);
  });

  it('marks nothing current when no section is active', () => {
    render(entry('/system'), null);
    expect(tabs()).toEqual([['Health', '/system'], ['Versions', '/system/versions']]);
    expect(el().querySelector('[aria-current]')).toBeNull();
  });

  it("grows each segment to the hit size and reuses sb-segmented's tokens, no literal colour", () => {
    expect(SOURCE).toMatch(/\.segment \{[^}]*min-height: var\(--control-h\)/);
    expect(SOURCE).toMatch(/\.segment \{[^}]*min-width: var\(--hit-min\)/);
    expect(SOURCE).toMatch(/\.current \{[^}]*background: var\(--accent-soft\)/);
    expect(SOURCE).toMatch(/\.track \{[^}]*overflow-x: auto/);
    expect(SOURCE).not.toMatch(/#[0-9a-f]{3,8}\b|rgba?\(/i);
  });

  it('is drawn by the shell alone: no workspace renders it', () => {
    const drawers = allSources()
      .filter((file) => file.name.startsWith('app/workspaces/') && file.source.includes('sb-section-tabs'))
      .map((file) => file.name);
    expect(drawers).toEqual([]);
  });
});
