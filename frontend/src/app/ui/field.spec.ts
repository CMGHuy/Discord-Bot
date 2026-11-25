import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { Component, inject, provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { Field, FieldSize, SB_FIELD } from './field';
import { resolveToken } from './testing/resolve-token';

const SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/field.ts'), 'utf8');
const PHONE = SOURCE.match(/@media \(max-width: 639px\) \{([\s\S]*?)\n {4}\}/)?.[1] ?? '';

/** Stands in for sb-select / sb-text-input: reads the field context the way they will (V246-4). */
@Component({ selector: 'sb-probe', template: '{{ ctx?.label() ?? "none" }}' })
class Probe {
  readonly ctx = inject(SB_FIELD, { optional: true });
}

@Component({
  imports: [Field, Probe],
  template: `
    <sb-field [label]="label()" [size]="size()" [fullRow]="fullRow()">
      <sb-probe id="probe" />
    </sb-field>
  `,
})
class Host {
  readonly label = signal('Strategy');
  readonly size = signal<FieldSize>('m');
  readonly fullRow = signal(false);
}

function host(setup: (h: Host) => void = () => {}) {
  const f = TestBed.createComponent(Host);
  setup(f.componentInstance);
  f.detectChanges();
  const el = f.nativeElement as HTMLElement;
  return { f, el, field: el.querySelector('sb-field') as HTMLElement };
}

describe('Field (v246 §A2)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('draws the label line above the projected control', () => {
    const { field } = host();
    const label = field.querySelector('.field-label')!;
    expect(label.textContent!.trim()).toBe('Strategy');
    expect(label.classList).toContain('sb-label');
    expect(field.firstElementChild).toBe(label);
    expect(field.querySelector('#probe')).not.toBeNull();
  });

  it('keeps an empty label line as an aria-hidden filler, so every field in a bar is one height', () => {
    const { field } = host((h) => h.label.set(''));
    const filler = field.querySelector('.field-label')!;
    expect(filler.classList).toContain('filler');
    expect(filler.textContent).toBe(' ');
    expect(filler.getAttribute('aria-hidden')).toBe('true');
    expect(field.classList).toContain('no-label');
  });

  it('hides its visible label from assistive tech: the wrapped control carries the name', () => {
    const { field } = host();
    expect(field.querySelector('.field-label')!.getAttribute('aria-hidden')).toBe('true');
    expect(field.classList).not.toContain('no-label');
  });

  it('hands its label to the projected control through SB_FIELD, and follows changes', () => {
    const { f, el } = host();
    expect(el.querySelector('#probe')!.textContent).toBe('Strategy');
    f.componentInstance.label.set('Horizon');
    f.detectChanges();
    expect(el.querySelector('#probe')!.textContent).toBe('Horizon');
  });

  it('provides no field context outside a field', () => {
    const probe = TestBed.createComponent(Probe);
    probe.detectChanges();
    expect(probe.componentInstance.ctx).toBeNull();
    expect((probe.nativeElement as HTMLElement).textContent).toBe('none');
  });

  it('exposes its size as data-size, M by default, and its full-row flag as a class', () => {
    const bare = TestBed.createComponent(Field);
    bare.detectChanges();
    expect((bare.nativeElement as HTMLElement).getAttribute('data-size')).toBe('m');

    const { field } = host((h) => { h.size.set('auto'); h.fullRow.set(true); });
    expect(field.getAttribute('data-size')).toBe('auto');
    expect(field.classList).toContain('full-row');
  });

  it('maps each size to its width token and leaves auto to the control', () => {
    expect(SOURCE).toMatch(/:host\(\[data-size='s'\]\) \{ --sb-control-w: var\(--field-s\); \}/);
    expect(SOURCE).toMatch(/:host\(\[data-size='m'\]\) \{ --sb-control-w: var\(--field-m\); \}/);
    expect(SOURCE).toMatch(/:host\(\[data-size='l'\]\) \{ --sb-control-w: var\(--field-l\); \}/);
    expect(SOURCE).toMatch(/:host\(\[data-size='auto'\]\) \{ --sb-control-w: initial; \}/);
  });

  it('stacks label over control with the shared gap, never centring them', () => {
    const rule = SOURCE.match(/\n {4}:host \{[^}]*\}/)?.[0] ?? '';
    expect(rule).toContain('flex-direction: column');
    expect(rule).toContain('gap: var(--space-4)');
    expect(rule).toContain('min-width: 0');
    expect(rule).not.toContain('align-items: center');
  });

  it('fills its row or cell below 640px, and a full-row field drops its empty filler there', () => {
    expect(PHONE).toMatch(/:host\(:not\(\[data-size='auto'\]\)\) \{ --sb-control-w: 100%; \}/);
    expect(PHONE).toMatch(/:host\(\.full-row\) \{[^}]*width: 100%/);
    expect(PHONE).toMatch(/:host\(\.full-row\.no-label\) \.field-label \{ display: none; \}/);
  });

  it('reads real width tokens', () => {
    expect(resolveToken('--field-s')).toBe('136px');
    expect(resolveToken('--field-m')).toBe('176px');
    expect(resolveToken('--field-l')).toBe('240px');
  });
});
