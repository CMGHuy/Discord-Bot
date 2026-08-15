import { Component, provideZonelessChangeDetection, signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { Button } from './button';
import { ConfirmDialog } from './confirm-dialog';
import { FilterBar, FilterChip, FilterChips } from './filter-bar';
import { Checkbox, Select, TextInput } from './form-controls';
import { installDialogPolyfill } from '../testing/dialog-polyfill';
import { ControlRow, Drawer, Tab, TabBar } from './layout';

/* NG41 — input and layout.
 *
 * Concentrated on the three things that are behaviour rather than paint: the
 * confirm dialog's insistence on naming a consequence, the tab strip's
 * keyboard handling, and the modal open/close plumbing. Styling is not
 * asserted anywhere.
 */

const CHIPS: FilterChip[] = [
  { value: 'open', label: 'Open', count: 4 },
  { value: 'win', label: 'Win' },
];

const TABS: Tab[] = [
  { id: 'plan', label: 'Plan' },
  { id: 'live', label: 'Live' },
  { id: 'chart', label: 'Chart' },
];

@Component({
  imports: [
    Button,
    ConfirmDialog,
    FilterBar,
    FilterChips,
    Select,
    TextInput,
    Checkbox,
    TabBar,
    Drawer,
    ControlRow,
  ],
  template: `
    <button sb-button [variant]="variant()" [loading]="working()" (click)="onClick()">Go</button>

    <sb-filter-bar [activeCount]="activeCount()" (cleared)="onCleared()">
      <sb-select [(value)]="strategy" [options]="[{ value: 'rsi', label: 'RSI' }]" label="Strategy" />
      <sb-text-input [(value)]="ticker" label="Ticker" />
      <sb-checkbox [(checked)]="noted" label="Has note" />
    </sb-filter-bar>

    <!-- Placed AFTER the filter bar on purpose: the existing checkbox
         assertions use querySelector, which takes the first match in document
         order, so the bare checkbox above stays the one they mean. -->
    <sb-checkbox label="Only changed" topLabel="Filter" [(checked)]="flagged" />

    <sb-filter-chips [chips]="chips" [selected]="status()" (selectedChange)="status.set($event)" />

    <sb-tab-bar [tabs]="tabs" [active]="tab()" (activeChange)="tab.set($event)" />

    <sb-confirm-dialog
      [open]="confirmOpen()"
      title="Delete trade"
      consequence="AAPL, opened 3 Jan. Its notes and history are deleted permanently."
      (confirmed)="onConfirmed()"
      (cancelled)="onCancelled()"
    />

    <sb-drawer [open]="drawerOpen()" heading="Details" (closed)="drawerOpen.set(false)" />

    <sb-control-row>
      <sb-text-input label="Search" [(value)]="query" />
      <button sb-button>Go</button>
    </sb-control-row>
    <sb-control-row [stacked]="true"><button sb-button>Kill</button></sb-control-row>
  `,
})
class Host {
  readonly variant = signal<'primary' | 'danger'>('primary');
  readonly working = signal(false);
  readonly activeCount = signal(0);
  readonly chips = CHIPS;
  readonly tabs = TABS;
  readonly status = signal<string | null>(null);
  readonly tab = signal('plan');
  readonly confirmOpen = signal(false);
  readonly drawerOpen = signal(false);

  readonly strategy = signal('');
  readonly ticker = signal('');
  readonly noted = signal(false);
  readonly flagged = signal(false);
  readonly query = signal('');

  clicks = 0;
  cleared = 0;
  confirmed = 0;
  cancelled = 0;

  // Angular template expressions have no `++` and no statement sequences,
  // so the counters are bumped through methods.
  onClick(): void {
    this.clicks += 1;
  }
  onCleared(): void {
    this.cleared += 1;
  }
  onConfirmed(): void {
    this.confirmed += 1;
  }
  onCancelled(): void {
    this.cancelled += 1;
    this.confirmOpen.set(false);
  }
}

describe('input and layout components', () => {
  let fixture: ComponentFixture<Host>;
  let host: Host;

  beforeEach(() => {
    // jsdom has no showModal()/close(); see the polyfill for why `<dialog>`
    // stays anyway.
    installDialogPolyfill();
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    fixture = TestBed.createComponent(Host);
    host = fixture.componentInstance;
    fixture.detectChanges();
  });

  const el = (): HTMLElement => fixture.nativeElement;
  const q = <T extends Element>(selector: string) => el().querySelector(selector) as T;

  /* -- button ------------------------------------------------------------ */

  it('paints a real button element rather than wrapping one', () => {
    // The element in the DOM is the button the browser knows how to operate.
    const button = q<HTMLButtonElement>('button[sb-button]');
    expect(button.tagName).toBe('BUTTON');
    expect(button.className).toContain('primary');
  });

  it('locks while a command is in flight so it cannot be sent twice', () => {
    host.working.set(true);
    fixture.detectChanges();

    const button = q<HTMLButtonElement>('button[sb-button]');
    expect(button.disabled).toBe(true);
    expect(button.getAttribute('aria-busy')).toBe('true');

    button.click();
    expect(host.clicks).toBe(0);
  });

  /* -- filters ------------------------------------------------------------ */

  it('says nothing about filters when none are on', () => {
    expect(el().textContent).not.toContain('active');
    expect(el().textContent).not.toContain('Clear all');
  });

  it('states how many filters are on and offers one click to clear them', () => {
    // A filtered table that looks like an empty one is the main way a list
    // tool wastes an afternoon.
    host.activeCount.set(3);
    fixture.detectChanges();

    expect(q('.active').textContent).toContain('3 active');
    [...el().querySelectorAll('button')]
      .find((b) => b.textContent!.includes('Clear all'))!
      .click();
    expect(host.cleared).toBe(1);
  });

  it('always offers a route back to unfiltered', () => {
    host.status.set('open');
    fixture.detectChanges();

    const all = q<HTMLButtonElement>('sb-filter-chips .chip');
    expect(all.textContent!.trim()).toBe('All');
    all.click();
    fixture.detectChanges();

    expect(host.status()).toBeNull();
  });

  it('marks the selected chip as pressed, and only that one', () => {
    host.status.set('open');
    fixture.detectChanges();

    const pressed = [...el().querySelectorAll('sb-filter-chips .chip')].map((c) =>
      c.getAttribute('aria-pressed'),
    );
    expect(pressed).toEqual(['false', 'true', 'false']);
  });

  it('shows a chip count only when the store supplied one', () => {
    const chips = [...el().querySelectorAll('sb-filter-chips .chip')];
    expect(chips[1].textContent).toContain('4');
    expect(chips[2].querySelector('.count')).toBeNull();
  });

  /* -- form controls ------------------------------------------------------ */

  it('binds a select, a text input and a checkbox two ways', () => {
    const select = q<HTMLSelectElement>('sb-select select');
    select.value = 'rsi';
    select.dispatchEvent(new Event('change'));
    expect(host.strategy()).toBe('rsi');

    const input = q<HTMLInputElement>('sb-text-input input');
    input.value = 'AAPL';
    input.dispatchEvent(new Event('input'));
    expect(host.ticker()).toBe('AAPL');

    q<HTMLInputElement>('sb-checkbox input').click();
    expect(host.noted()).toBe(true);
  });

  it('associates every control with a real label element', () => {
    // Clicking the text focuses the control, and the accessibility tree gets
    // the association without an aria attribute to keep in sync.
    expect(q('sb-select label')).not.toBeNull();
    expect(q('sb-text-input label')).not.toBeNull();
    expect(q('sb-checkbox label')).not.toBeNull();
  });

  it('renders a top label above the box when one is given', () => {
    const top = fixture.nativeElement.querySelector('sb-checkbox .top-label');
    expect(top?.textContent?.trim()).toBe('Filter');
  });

  it('keeps the inline caption as the checkbox own name', () => {
    // Scoped to the checkbox that HAS a top label -- the template holds two,
    // and the bare one in the filter bar is first in document order.
    const boxes: Element[] = Array.from(
      fixture.nativeElement.querySelectorAll('sb-checkbox'),
    );
    const stacked = boxes.find((el) => el.querySelector('.top-label'));
    const caption = stacked?.querySelector('.box span');
    expect(caption?.textContent?.trim()).toBe('Only changed');
  });

  /* -- control row -------------------------------------------------------- */

  it('projects its controls', () => {
    const row = fixture.nativeElement.querySelector('sb-control-row .row');
    expect(row?.querySelector('sb-text-input')).toBeTruthy();
    expect(row?.querySelector('button[sb-button]')).toBeTruthy();
  });

  it('marks a stacked row so it can collapse at narrow widths', () => {
    const rows = fixture.nativeElement.querySelectorAll('sb-control-row .row');
    expect(rows[0].classList.contains('stacked')).toBe(false);
    expect(rows[1].classList.contains('stacked')).toBe(true);
  });

  it('omits the top label element entirely when unset', () => {
    const bare = fixture.nativeElement.querySelectorAll('sb-checkbox');
    // The template's other checkbox has no topLabel.
    const without = Array.from(bare).find(
      (el) => !(el as Element).querySelector('.top-label'),
    );
    expect(without).toBeTruthy();
  });

  /* -- tab bar ------------------------------------------------------------ */

  it('exposes the strip as a tablist with one selected tab', () => {
    expect(q('[role=tablist]')).not.toBeNull();
    const selected = [...el().querySelectorAll('[role=tab]')].map((t) =>
      t.getAttribute('aria-selected'),
    );
    expect(selected).toEqual(['true', 'false', 'false']);
  });

  it('keeps exactly one tab in the tab order', () => {
    const indexes = [...el().querySelectorAll('[role=tab]')].map((t) =>
      t.getAttribute('tabindex'),
    );
    expect(indexes).toEqual(['0', '-1', '-1']);
  });

  it('moves between tabs with the arrow keys', () => {
    q('[role=tablist]').dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight' }));
    fixture.detectChanges();
    expect(host.tab()).toBe('live');
  });

  it('wraps around rather than dead-ending at the strip edge', () => {
    q('[role=tablist]').dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowLeft' }));
    fixture.detectChanges();
    expect(host.tab()).toBe('chart');
  });

  it('ignores keys that are not arrows', () => {
    q('[role=tablist]').dispatchEvent(new KeyboardEvent('keydown', { key: 'a' }));
    fixture.detectChanges();
    expect(host.tab()).toBe('plan');
  });

  /* -- confirm dialog ----------------------------------------------------- */

  it('names what is being destroyed instead of asking "are you sure"', () => {
    // The whole reason the component exists. `consequence` is a required
    // input so a call site cannot omit it and get a generic dialog.
    host.confirmOpen.set(true);
    fixture.detectChanges();

    const text = q('sb-confirm-dialog').textContent!;
    expect(text).toContain('AAPL, opened 3 Jan');
    expect(text).toContain('deleted permanently');
    expect(text.toLowerCase()).not.toContain('are you sure');
  });

  it('opens and closes the native dialog from the input', () => {
    const dialog = q<HTMLDialogElement>('sb-confirm-dialog dialog');
    expect(dialog.open).toBe(false);

    host.confirmOpen.set(true);
    fixture.detectChanges();
    expect(dialog.open).toBe(true);

    host.confirmOpen.set(false);
    fixture.detectChanges();
    expect(dialog.open).toBe(false);
  });

  it('defaults the confirm action to the danger variant', () => {
    host.confirmOpen.set(true);
    fixture.detectChanges();

    const confirm = [...el().querySelectorAll('sb-confirm-dialog button')].at(-1)!;
    expect(confirm.className).toContain('danger');
  });

  it('routes cancelling and dismissing down the same path', () => {
    host.confirmOpen.set(true);
    fixture.detectChanges();

    const cancel = q<HTMLButtonElement>('sb-confirm-dialog button');
    cancel.click();
    fixture.detectChanges();

    expect(host.cancelled).toBe(1);
    expect(host.confirmed).toBe(0);
    expect(q<HTMLDialogElement>('sb-confirm-dialog dialog').open).toBe(false);
  });

  /* -- drawer -------------------------------------------------------------- */

  it('opens the drawer as a modal and reports its own dismissal', () => {
    const drawer = q<HTMLDialogElement>('sb-drawer dialog');

    host.drawerOpen.set(true);
    fixture.detectChanges();
    expect(drawer.open).toBe(true);

    q<HTMLButtonElement>('sb-drawer .close').click();
    fixture.detectChanges();

    expect(host.drawerOpen()).toBe(false);
    expect(drawer.open).toBe(false);
  });
});
