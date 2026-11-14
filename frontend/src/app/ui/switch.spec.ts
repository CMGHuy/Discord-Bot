import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { Component, provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { Switch } from './switch';

@Component({
  imports: [Switch],
  template: `
    <sb-switch [label]="label" [checked]="checked()" [mixed]="mixed()" [disabled]="disabled()" [hint]="hint()"
               (checkedChange)="changes.push($event); checked.set($event); mixed.set(false)" />
  `,
})
class Host {
  label = 'Order filled';
  readonly checked = signal(false);
  readonly mixed = signal(false);
  readonly disabled = signal(false);
  readonly hint = signal<string | null>(null);
  readonly changes: boolean[] = [];
}

describe('Switch (v227)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  function mount(setup: (host: Host) => void = () => undefined) {
    const fixture = TestBed.createComponent(Host);
    setup(fixture.componentInstance);
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    return { fixture, host: fixture.componentInstance, el, button: el.querySelector('button')! };
  }

  it('is a button with role switch, named by its visible label', () => {
    const { button } = mount();
    expect(button.getAttribute('type')).toBe('button');
    expect(button.getAttribute('role')).toBe('switch');
    expect(button.textContent!.trim()).toBe('Order filled');
    expect(button.hasAttribute('aria-label')).toBe(false);
    expect(button.hasAttribute('title')).toBe(false);
  });

  it('reports aria-checked true, false and mixed', () => {
    const { fixture, host, button } = mount();
    expect(button.getAttribute('aria-checked')).toBe('false');
    host.checked.set(true);
    fixture.detectChanges();
    expect(button.getAttribute('aria-checked')).toBe('true');
    host.mixed.set(true);
    fixture.detectChanges();
    expect(button.getAttribute('aria-checked')).toBe('mixed');
  });

  it('emits the flipped value on a click and follows the parent', () => {
    const { fixture, host, button } = mount();
    button.click();
    fixture.detectChanges();
    expect(host.changes).toEqual([true]);
    expect(button.getAttribute('aria-checked')).toBe('true');
    button.click();
    expect(host.changes).toEqual([true, false]);
  });

  it('turns a mixed switch fully on', () => {
    const { host, button } = mount((h) => {
      h.checked.set(false);
      h.mixed.set(true);
    });
    button.click();
    expect(host.changes).toEqual([true]);
  });

  it('is really disabled: the attribute is set and a click emits nothing', () => {
    const { host, button } = mount((h) => h.disabled.set(true));
    expect(button.disabled).toBe(true);
    button.click();
    expect(host.changes).toEqual([]);
  });

  it('ties an optional hint line to the control', () => {
    const none = mount();
    expect(none.button.hasAttribute('aria-describedby')).toBe(false);
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    const { el, button } = mount((h) => h.hint.set('Says: Order filled, <ticker>'));
    const id = button.getAttribute('aria-describedby')!;
    expect(el.querySelector(`#${id}`)!.textContent!.trim()).toBe('Says: Order filled, <ticker>');
  });

  it('gives each switch its own hint id', () => {
    const a = mount((h) => h.hint.set('a')).button.getAttribute('aria-describedby');
    const b = mount((h) => h.hint.set('b')).button.getAttribute('aria-describedby');
    expect(a).not.toBe(b);
  });

  it('is at least --hit-min tall, lets the label wrap, and uses tokens only', () => {
    const source = readFileSync(join(process.cwd(), 'src/app/ui/switch.ts'), 'utf8');
    expect(source).toMatch(/\.switch \{[^}]*min-height: var\(--hit-min\);/);
    expect(source).not.toMatch(/text-overflow|white-space: nowrap/);
    expect(source).not.toMatch(/pointer: coarse/);
    expect(source).not.toMatch(/#[0-9a-fA-F]{3,8}\b|rgba?\(/);
  });
});
