import { Component, provideZonelessChangeDetection, signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { describe, beforeEach, expect, it } from 'vitest';

import { Viewport } from './breakpoints';
import { Toolbar, ToolbarControl } from './toolbar';

@Component({
  imports: [Toolbar],
  template: `
    <sb-toolbar [controls]="controls()" [viewportAt]="viewportAt()">
      <button slot="status">Status</button>
      <button slot="ticker">Ticker</button>
      <button slot="badge">Badge</button>
    </sb-toolbar>
  `,
})
class Host {
  readonly viewportAt = signal<Viewport | null>(null);
  readonly controls = signal<ToolbarControl[]>([
    { id: 'status', label: 'Status' },
    { id: 'ticker', label: 'Ticker', inlineFrom: 'md' },
    { id: 'badge', label: 'Badge', inlineFrom: 'md' },
  ]);
}

describe('sb-toolbar', () => {
  let fixture: ComponentFixture<Host>;
  let host: Host;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    fixture = TestBed.createComponent(Host);
    host = fixture.componentInstance;
    host.viewportAt.set('sm');
    fixture.detectChanges();
  });

  const el = () => fixture.nativeElement as HTMLElement;

  it('keeps above-floor controls inline', () => {
    expect(el().querySelector('.toolbar-inline [slot="status"]')).not.toBeNull();
  });

  it('moves below-floor controls into the sheet, not out of the DOM', () => {
    expect(el().querySelector('.toolbar-inline [slot="ticker"]')).toBeNull();
    expect(el().querySelector('.toolbar-sheet [slot="ticker"]')).not.toBeNull();
  });

  it('starts with the sheet closed', () => {
    expect(el().querySelector('.toolbar-sheet-button')!.getAttribute('aria-expanded'))
      .toBe('false');
  });

  it('offers no sheet button when nothing is demoted', () => {
    host.viewportAt.set('xl');
    fixture.detectChanges();
    expect(el().querySelector('.toolbar-sheet-button')).toBeNull();
  });

  it('names how many demoted controls it holds', () => {
    expect(el().querySelector('.toolbar-sheet-button')!.textContent).toContain('2');
  });

  it('moves the same element back inline rather than rebuilding it', () => {
    // The node identity is the point: a control destroyed and recreated at a
    // breakpoint loses its focus, its open dropdown and any uncommitted text.
    const demoted = el().querySelector('.toolbar-sheet [slot="ticker"]');
    host.viewportAt.set('xl');
    fixture.detectChanges();
    expect(el().querySelector('.toolbar-inline [slot="ticker"]')).toBe(demoted);
  });
});

describe('sb-toolbar active badge', () => {
  let fixture: ComponentFixture<Host>;
  let host: Host;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    fixture = TestBed.createComponent(Host);
    host = fixture.componentInstance;
    host.viewportAt.set('sm');
    fixture.detectChanges();
  });

  const el = () => fixture.nativeElement as HTMLElement;
  const button = () => el().querySelector('.toolbar-sheet-button')!;

  it('shows no active marker when every demoted control is at its default', () => {
    expect(el().querySelector('.active-dot')).toBeNull();
    expect(button().getAttribute('aria-label')).toBe('Filters — 2 hidden');
  });

  it('marks the sheet when a demoted control is engaged', () => {
    host.controls.set([
      { id: 'status', label: 'Status' },
      { id: 'ticker', label: 'Ticker', inlineFrom: 'md', active: true },
      { id: 'badge', label: 'Badge', inlineFrom: 'md' },
    ]);
    fixture.detectChanges();
    expect(el().querySelector('.active-dot')).not.toBeNull();
    expect(button().getAttribute('aria-label')).toBe('Filters — 2 hidden, 1 active');
  });

  it('counts only DEMOTED actives — an inline active is already visible', () => {
    host.controls.set([
      { id: 'status', label: 'Status', active: true },
      { id: 'ticker', label: 'Ticker', inlineFrom: 'md' },
      { id: 'badge', label: 'Badge', inlineFrom: 'md' },
    ]);
    fixture.detectChanges();
    expect(el().querySelector('.active-dot')).toBeNull();
  });
});
