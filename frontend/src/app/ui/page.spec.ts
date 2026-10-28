import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { Component, Type, provideZonelessChangeDetection, signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { beforeAll, beforeEach, describe, expect, it } from 'vitest';

import { RouteTitleService } from '../routing/route-title.service';
import { focusWorkspaceHeading } from '../shell/route-focus';
import { installDialogPolyfill } from '../testing/dialog-polyfill';
import { Button } from './button';
import { ConfirmDialog } from './confirm-dialog';
import { Page } from './page';

@Component({
  imports: [Page],
  template: `
    <sb-page>
      <span page-actions class="probe-action">Export</span>
      <div page-scope class="probe-scope">Scope</div>
      <div page-kpis class="probe-kpis">KPIs</div>
      <div page-primary class="probe-primary">Primary</div>
      <div page-secondary class="probe-secondary">A</div>
      <div page-secondary class="probe-secondary">B</div>
    </sb-page>
  `,
})
class EverySlot {}

@Component({
  imports: [Page],
  template: `
    <sb-page heading="Risk" description="Open exposure against the cap">
      <div page-primary class="probe-primary">Heat</div>
    </sb-page>
  `,
})
class PrimaryOnly {}

@Component({ imports: [Page], template: `<sb-page />` })
class RouteTitled {}

@Component({
  imports: [Page],
  template: `<main class="workspace"><sb-page><div page-primary>Table</div></sb-page></main>`,
})
class InWorkspace {}

@Component({
  imports: [Page, Button, ConfirmDialog],
  template: `
    <sb-page heading="System">
      <button sb-button variant="danger-quiet" type="button" page-actions class="restart" (click)="asking.set(true)">
        Restart bot
      </button>
      <div page-primary>Logs</div>
      <sb-confirm-dialog
        [open]="asking()"
        title="Restart the bot?"
        consequence="Scans stop until it is back."
        confirmLabel="Restart"
        dangerVariant="danger-quiet"
        (confirmed)="onConfirmed()"
        (cancelled)="asking.set(false)"
      />
    </sb-page>
  `,
})
class WithDestructive {
  readonly asking = signal(false);
  confirmed = 0;
  onConfirmed(): void {
    this.confirmed += 1;
    this.asking.set(false);
  }
}

const pageSource = () => readFileSync(join(process.cwd(), 'src/app/ui/page.ts'), 'utf8');

describe('sb-page (v195 Phase 4)', () => {
  beforeAll(() => installDialogPolyfill());

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  async function render<T>(host: Type<T>): Promise<{ fixture: ComponentFixture<T>; el: HTMLElement }> {
    const fixture = TestBed.createComponent(host);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    return { fixture, el: fixture.nativeElement as HTMLElement };
  }

  it("renders the page's one h1 from the route title, and the route subtitle as its description", async () => {
    TestBed.inject(RouteTitleService).set('Risk', 'Open exposure against the cap');
    const { el } = await render(RouteTitled);
    expect(el.querySelectorAll('h1')).toHaveLength(1);
    expect(el.querySelector('header.bar .heading h1.title')!.textContent!.trim()).toBe('Risk');
    expect(el.querySelector('.description')!.textContent!.trim()).toBe('Open exposure against the cap');
  });

  it('lets the heading and description inputs win over the route', async () => {
    TestBed.inject(RouteTitleService).set('Something else', 'Another line');
    const { el } = await render(PrimaryOnly);
    expect(el.querySelector('h1')!.textContent!.trim()).toBe('Risk');
    expect(el.querySelector('.description')!.textContent!.trim()).toBe('Open exposure against the cap');
  });

  it('renders no description element when there is none', async () => {
    TestBed.inject(RouteTitleService).set('Versions', null);
    const { el } = await render(RouteTitled);
    expect(el.querySelector('h1')!.textContent!.trim()).toBe('Versions');
    expect(el.querySelector('.description')).toBeNull();
  });

  it('follows the route title when it changes', async () => {
    const titles = TestBed.inject(RouteTitleService);
    titles.set('Trades', null);
    const { fixture, el } = await render(RouteTitled);
    titles.set('Calendar', 'Every trading day');
    fixture.detectChanges();
    expect(el.querySelector('h1')!.textContent!.trim()).toBe('Calendar');
  });

  it('projects each slot into its own region, in the spec order', async () => {
    const { el } = await render(EverySlot);
    const page = el.querySelector('sb-page')!;
    expect([...page.children].map((child) => child.classList[0])).toEqual(['bar', 'scope', 'kpis', 'primary', 'secondary']);
    expect(page.querySelector('header.bar > .actions > .probe-action')).not.toBeNull();
    expect(page.querySelector('.scope > .probe-scope')).not.toBeNull();
    expect(page.querySelector('.kpis > .probe-kpis')).not.toBeNull();
    expect(page.querySelector('.primary > .probe-primary')).not.toBeNull();
    expect(page.querySelectorAll('.secondary > .probe-secondary')).toHaveLength(2);
  });

  it('takes no space for an empty slot', async () => {
    const { el } = await render(PrimaryOnly);
    const page = el.querySelector('sb-page')!;
    for (const name of ['actions', 'scope', 'kpis', 'secondary']) {
      expect(page.querySelector(`.${name}`)!.matches(':empty'), name).toBe(true);
    }
    expect(page.querySelector('.primary')!.matches(':empty')).toBe(false);
    expect(pageSource()).toContain('.slot:empty { display: none; }');
  });

  it('lays the secondary grid out in two columns from lg (1440px) and one below', () => {
    const source = pageSource();
    expect(source).toMatch(/\.secondary \{[^}]*grid-template-columns: minmax\(0, 1fr\);/);
    expect(source).toMatch(/@media \(min-width: 1440px\) \{\s*\.secondary \{ grid-template-columns: repeat\(2, minmax\(0, 1fr\)\); \}/);
  });

  it('keeps a destructive action in the header and opens the confirm dialog from it', async () => {
    const { fixture, el } = await render(WithDestructive);
    const restart = el.querySelector<HTMLButtonElement>('sb-page header.bar .actions button.restart')!;
    expect(restart.classList).toContain('danger-quiet');
    const dialog = el.querySelector('dialog')!;
    expect(dialog.hasAttribute('open')).toBe(false);

    restart.click();
    fixture.detectChanges();
    await fixture.whenStable();
    expect(dialog.hasAttribute('open')).toBe(true);
    const confirm = [...dialog.querySelectorAll<HTMLButtonElement>('button')]
      .find((button) => button.textContent!.trim() === 'Restart')!;
    expect(confirm.classList).toContain('danger-quiet');

    confirm.click();
    fixture.detectChanges();
    expect(fixture.componentInstance.confirmed).toBe(1);
  });

  it('projects anything without a slot after the grid, so dialogs need no slot of their own', async () => {
    const { el } = await render(WithDestructive);
    const page = el.querySelector('sb-page')!;
    expect(page.lastElementChild!.tagName.toLowerCase()).toBe('sb-confirm-dialog');
  });

  it('is the heading route focus lands on inside the workspace', async () => {
    TestBed.inject(RouteTitleService).set('Trades', null);
    const { el } = await render(InWorkspace);
    focusWorkspaceHeading(document);
    const heading = el.querySelector('sb-page h1')!;
    expect(document.activeElement).toBe(heading);
    expect(heading.getAttribute('tabindex')).toBe('-1');
  });

  it('paints no surface of its own: the panels inside it do', () => {
    const styles = pageSource().slice(pageSource().indexOf('styles:'));
    expect(styles).not.toMatch(/background|box-shadow|border:/);
  });
});
