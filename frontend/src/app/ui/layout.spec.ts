import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { Component, provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { Panel, Tab, TabBar } from './layout';

const SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/layout.ts'), 'utf8');
const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const rule = (selector: string) => SOURCE.match(new RegExp(`${esc(selector)}\\s*\\{[^}]*\\}`))?.[0] ?? '';

@Component({ imports: [TabBar], template: `<sb-tab-bar [tabs]="tabs" [active]="'plans'" />` })
class TabHost {
  readonly tabs: Tab[] = [
    { id: 'plans', label: 'Plans' }, { id: 'strategies', label: 'Strategies' }, { id: 'tuning', label: 'Tuning' },
  ];
}

function geometry(el: HTMLElement, scrollWidth: number, clientWidth: number, scrollLeft: number) {
  Object.defineProperty(el, 'scrollWidth', { configurable: true, value: scrollWidth });
  Object.defineProperty(el, 'clientWidth', { configurable: true, value: clientWidth });
  Object.defineProperty(el, 'scrollLeft', { configurable: true, value: scrollLeft });
}

describe('sb-tab-bar overflow (v80 D4)', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));
  function mount() {
    const f = TestBed.createComponent(TabHost); f.detectChanges();
    const el = f.nativeElement as HTMLElement;
    return { f, tabs: el.querySelector('.tabs') as HTMLElement, strip: el.querySelector('.strip')! };
  }
  it('scrolls sideways instead of clipping a tab', () => {
    expect(rule('.tabs')).toContain('overflow-x: auto');
    expect(rule('.tab')).toContain('flex: 0 0 auto');
    expect(rule('.tab')).toContain('white-space: nowrap');
  });
  it('fades the far edge while more tabs sit off-screen', () => {
    const { f, tabs, strip } = mount(); geometry(tabs, 600, 300, 0); tabs.dispatchEvent(new Event('scroll')); f.detectChanges();
    expect(strip.classList).toContain('fade-end'); expect(strip.classList).not.toContain('fade-start');
  });
  it('fades the near edge once scrolled to the end', () => {
    const { f, tabs, strip } = mount(); geometry(tabs, 600, 300, 300); tabs.dispatchEvent(new Event('scroll')); f.detectChanges();
    expect(strip.classList).toContain('fade-start'); expect(strip.classList).not.toContain('fade-end');
  });
  it('shows no fade when every tab fits', () => {
    const { f, tabs, strip } = mount(); geometry(tabs, 300, 300, 0); tabs.dispatchEvent(new Event('scroll')); f.detectChanges();
    expect(strip.classList).not.toContain('fade-start'); expect(strip.classList).not.toContain('fade-end');
  });
  it('sizes tabs from --control-h, so they are 44px on touch', () => expect(rule('.tab')).toContain('min-height: var(--control-h)'));

  it('renders an icon and keeps the label for a tab that opts in, neither for one that does not', () => {
    @Component({
      imports: [TabBar],
      template: `<sb-tab-bar [tabs]="tabs" [active]="'plans'" />`,
    })
    class IconedHost {
      readonly tabs: Tab[] = [
        { id: 'plans', label: 'Plans', icon: 'dashboard' },
        { id: 'strategies', label: 'Strategies' },
      ];
    }
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    const f = TestBed.createComponent(IconedHost);
    f.detectChanges();
    const tabs = (f.nativeElement as HTMLElement).querySelectorAll('[role="tab"]');
    expect(tabs[0].querySelector('sb-icon')).not.toBeNull();
    expect(tabs[0].querySelector('.label')?.textContent).toBe('Plans');
    expect(tabs[0].getAttribute('aria-label')).toBe('Plans');
    expect(tabs[1].querySelector('sb-icon')).toBeNull();
    expect(tabs[1].getAttribute('aria-label')).toBeNull();
  });

  it('drops the label below sm for an iconed tab only, via CSS', () => {
    // 639px, not 640: breakpoints.ts's sm floor is 640px and the rule must
    // apply BELOW it, same convention shell.css's own mobile rules use.
    const block = SOURCE.match(/@media \(max-width: 639px\) \{([\s\S]*?)\n {4}\}/);
    expect(block).not.toBeNull();
    expect(block![1]).toContain('.tab.iconed .label { display: none; }');
  });
});

describe('sb-panel (v80 D4)', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));
  it('sets its heading in the shared label style', () => {
    const f = TestBed.createComponent(Panel); f.componentRef.setInput('heading', 'Exposure'); f.detectChanges();
    const h2 = (f.nativeElement as HTMLElement).querySelector('h2')!;
    expect(h2.classList).toContain('sb-label'); expect(h2.textContent!.trim()).toBe('Exposure');
  });
});

describe('sb-control-row and sb-drawer on a phone (v80 D4)', () => {
  it('stacks every control row below 640px', () => {
    expect(SOURCE).toMatch(/@media \(max-width: 639px\) \{\s*\.row \{ flex-direction: column; align-items: stretch; \}/);
    expect(SOURCE).not.toMatch(/\.stacked \{/);
  });
  it('sizes the drawer by the dynamic viewport', () => { expect(rule('.drawer')).toContain('height: 100dvh'); expect(rule('.drawer')).toContain('max-height: 100dvh'); });
  it('takes the full width on a phone', () => expect(SOURCE).toMatch(/@media \(max-width: 639px\) \{\s*\.drawer \{ width: 100vw; \}/));
  it('gives the close button a touch-sized target', () => expect(rule('.close')).toContain('min-height: var(--control-h)'));
});
