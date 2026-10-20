import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { Component, provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { ComponentFixture } from '@angular/core/testing';

import { Viewport } from './breakpoints';
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

  it('swaps the label for icon + count on a phone, via CSS', () => {
    const block = SOURCE.match(/@media \(max-width: 639px\) \{([\s\S]*?)\n {4}\}/);
    expect(block).not.toBeNull();
    expect(block![1]).toContain('.tab.iconed .label { display: none; }');
    expect(block![1]).toContain('.tab.iconed .count { display: inline; }');
    expect(block![1]).not.toContain('sb-icon { display: none; }');
  });

  it('renders "· N" next to the icon when a count is given, hidden by default', () => {
    @Component({
      imports: [TabBar],
      template: `<sb-tab-bar [tabs]="tabs" [active]="'plans'" />`,
    })
    class CountedHost {
      readonly tabs: Tab[] = [{ id: 'plans', label: 'Plans', icon: 'dashboard', count: 5 }];
    }
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    const f = TestBed.createComponent(CountedHost);
    f.detectChanges();
    const tab = (f.nativeElement as HTMLElement).querySelector('[role="tab"]')!;
    expect(tab.querySelector('.count')?.textContent).toBe('· 5');
    expect(rule('.count')).toContain('display: none');
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
  /* v168 §3a: below 640px the drawer is a bottom sheet, a geometry change
   * and not only a keyframe; from 640 to 1023px it takes 85vw from the right. */
  it('becomes a bottom sheet on a phone', () => {
    // Anchored on the .drawer rule: the control row has its own 639px block
    // earlier in the file.
    const phone = SOURCE.match(
      /@media \(max-width: 639px\) \{\s*\.drawer \{ margin: auto 0 0; width: 100vw; height: auto; max-height: 85dvh; \}([\s\S]*?)\n {4}\}/,
    );
    expect(phone).not.toBeNull();
    expect(phone![1]).toMatch(/\.drawer\.elev-overlay \{ border-radius: var\(--panel-radius\) var\(--panel-radius\) 0 0; border-width: 1px 0 0; \}/);
    expect(phone![1]).toMatch(/\.drag-handle \{ display: block;/);
    expect(rule('.drag-handle')).toContain('display: none');
  });
  it('takes 85vw from the right on a tablet', () =>
    expect(SOURCE).toMatch(/@media \(min-width: 640px\) and \(max-width: 1023px\) \{\s*\.drawer \{ width: 85vw; \}/));
  it('gives the close button a touch-sized target', () => expect(rule('.close')).toContain('min-height: var(--control-h)'));
});

@Component({
  imports: [Panel],
  template: `
    <sb-panel
      [heading]="heading()"
      [inlineFrom]="inlineFrom()"
      [digest]="digest()"
      [problem]="problem()"
      [viewportAt]="viewportAt()"
    >
      <p class="body-content">Body</p>
    </sb-panel>
  `,
})
class CollapseHost {
  readonly heading = signal('Watchlist');
  readonly inlineFrom = signal<Viewport | undefined>(undefined);
  readonly digest = signal<string | null>(null);
  readonly problem = signal<string | null>(null);
  readonly viewportAt = signal<Viewport | null>(null);
}

describe('sb-panel collapse', () => {
  let fixture: ComponentFixture<CollapseHost>;
  let host: CollapseHost;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    fixture = TestBed.createComponent(CollapseHost);
    host = fixture.componentInstance;
    fixture.detectChanges();
  });

  const el = () => fixture.nativeElement as HTMLElement;

  it('renders in full above its floor', () => {
    host.inlineFrom.set('md'); host.viewportAt.set('md'); fixture.detectChanges();
    expect(el().querySelector('.body')).not.toBeNull();
    expect(el().querySelector('.panel-digest')).toBeNull();
  });

  it('collapses to its digest below its floor', () => {
    host.inlineFrom.set('md'); host.digest.set('no priced symbols yet');
    host.viewportAt.set('sm'); fixture.detectChanges();
    expect(el().querySelector('.panel-digest')!.textContent)
      .toContain('no priced symbols yet');
    expect(el().querySelector('.body')).toBeNull();
  });

  it('expands in place on tap and keeps the digest out of the way', () => {
    host.inlineFrom.set('md'); host.digest.set('3 open');
    host.viewportAt.set('sm'); fixture.detectChanges();
    (el().querySelector('button.panel-toggle') as HTMLElement).click();
    fixture.detectChanges();
    expect(el().querySelector('.body')).not.toBeNull();
    expect(el().querySelector('button.panel-toggle')!.getAttribute('aria-expanded'))
      .toBe('true');
    expect(el().querySelector('.panel-digest')).toBeNull();
  });

  it('never collapses without a digest — an empty summary is worse than none', () => {
    host.inlineFrom.set('md'); host.digest.set(null);
    host.viewportAt.set('sm'); fixture.detectChanges();
    expect(el().querySelector('.body')).not.toBeNull();
    expect(el().querySelector('button.panel-toggle')).toBeNull();
  });

  it('keeps the title readable while collapsed', () => {
    host.inlineFrom.set('md'); host.digest.set('3 open');
    host.viewportAt.set('sm'); fixture.detectChanges();
    expect(el().textContent).toContain(host.heading());
  });
});

describe('sb-panel force-expand guard', () => {
  let fixture: ComponentFixture<CollapseHost>;
  let host: CollapseHost;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    fixture = TestBed.createComponent(CollapseHost);
    host = fixture.componentInstance;
    host.inlineFrom.set('md'); host.digest.set('3 open'); host.viewportAt.set('sm');
    fixture.detectChanges();
  });

  const el = () => fixture.nativeElement as HTMLElement;

  it('collapses normally when there is no problem', () => {
    expect(el().querySelector('.body')).toBeNull();
  });

  it('force-expands when the data is stale', () => {
    host.problem.set('stale — last updated 18:41');
    fixture.detectChanges();
    expect(el().querySelector('.body')).not.toBeNull();
  });

  it('says what the problem is rather than just opening', () => {
    host.problem.set('stale — last updated 18:41');
    fixture.detectChanges();
    expect(el().textContent).toContain('stale — last updated 18:41');
  });

  it('offers no collapse toggle while the problem stands', () => {
    // Letting the user re-collapse it would put the warning back behind a
    // digest that does not mention it.
    host.problem.set('failed to load');
    fixture.detectChanges();
    expect(el().querySelector('button.panel-toggle')).toBeNull();
  });
});

/* -- v95 C4 -- tab counts survive icon-only ------------------------------- */

describe('sb-tab-bar narrow widths', () => {
  it('shows the count beside the icon once the label is hidden', () => {
    expect(SOURCE).toMatch(/\.tab\.iconed \.label \{ display: none; \}/);
    expect(SOURCE).toMatch(/\.tab\.iconed \.count \{ display: inline; \}/);
  });
});

/** One component's styles: the source between its selector and its class. */
function stylesOf(selector: string, className: string): string {
  return SOURCE.slice(SOURCE.indexOf(`selector: '${selector}'`), SOURCE.indexOf(`export class ${className}`));
}
const ruleIn = (styles: string, selector: string) =>
  styles.match(new RegExp(`(?:^|\\n)\\s*${esc(selector)}\\s*\\{[^}]*\\}`))?.[0] ?? '';

describe('sb-panel header: one height, one baseline (v179 §3.3, §3.4)', () => {
  const PANEL = stylesOf('sb-panel', 'Panel');

  it('aligns label, counts, actions and hint on the text baseline, never their centres', () => {
    const header = ruleIn(PANEL, 'header');
    expect(header).toContain('align-items: baseline');
    expect(header).not.toContain('align-items: center');
    expect(ruleIn(PANEL, '.actions')).toContain('align-items: baseline');
  });

  it('gives every header one minimum height and centres its line in it', () => {
    const header = ruleIn(PANEL, 'header');
    expect(header).toContain('min-height: calc(var(--control-h) + 2 * var(--space-10) + 1px)');
    expect(header).toContain('flex-wrap: wrap');
    expect(header).toContain('align-content: center');
  });

  it('keeps one gap between the header and the first row of the body', () => {
    expect(PANEL).toContain(':host ::ng-deep .panel > .body > :first-child { margin-top: 0; }');
    expect(ruleIn(PANEL, '.body')).toContain('padding: var(--space-14)');
  });

  it('renders the actions slot inside the header, beside the label', () => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    const f = TestBed.createComponent(Panel);
    f.componentRef.setInput('heading', 'Exposure');
    f.detectChanges();
    const header = (f.nativeElement as HTMLElement).querySelector('header')!;
    expect([...header.children].map((child) => child.tagName.toLowerCase() + '.' + child.className))
      .toEqual(['h2.sb-label', 'div.actions']);
  });
});

describe('sb-control-row on the last baseline (v179 §3.4)', () => {
  const ROW = stylesOf('sb-control-row', 'ControlRow');

  it('aligns controls and plain text on one text line', () => {
    const row = ruleIn(ROW, '.row');
    expect(row).toContain('align-items: last baseline');
    expect(row).not.toContain('flex-end');
  });

  it('still stacks below 640px', () => {
    expect(ROW).toMatch(/@media \(max-width: 639px\) \{\s*\.row \{ flex-direction: column; align-items: stretch; \}/);
  });
});
