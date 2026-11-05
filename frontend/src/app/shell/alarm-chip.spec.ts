import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { AlarmChip } from './alarm-chip';
import { Alarm } from './live/live-state';

describe('AlarmChip (v203, spec v202 §3)', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));

  function render(alarm: Alarm | null) {
    const fixture = TestBed.createComponent(AlarmChip);
    fixture.componentRef.setInput('alarm', alarm);
    fixture.detectChanges();
    return { fixture, el: fixture.nativeElement as HTMLElement };
  }

  it('renders nothing when nothing is wrong', () => {
    const { el } = render(null);
    expect(el.querySelector('button')).toBeNull();
    expect(el.innerHTML.replace(/<!--[\s\S]*?-->/g, '').trim()).toBe('');
  });

  it.each<[Alarm, string]>([
    [{ kind: 'bot-down', text: 'Bot down' }, 'Bot down. Open the live dock'],
    [{ kind: 'disconnected', text: 'Disconnected' }, 'Disconnected. Open the live dock'],
    [{ kind: 'stale', text: 'Data stale 12 min' }, 'Data stale 12 min. Open the live dock'],
    [{ kind: 'stale', text: 'Data stale' }, 'Data stale. Open the live dock'],
  ])('names %o in words and in its accessible name', (alarm, label) => {
    const button = render(alarm).el.querySelector('button.alarm-chip')!;
    expect(button.querySelector('.text')!.textContent!.trim()).toBe(alarm.text);
    expect(button.getAttribute('aria-label')).toBe(label);
    expect(button.getAttribute('data-kind')).toBe(alarm.kind);
  });

  it('opens the dock on a tap', () => {
    const { fixture, el } = render({ kind: 'stale', text: 'Data stale 20 min' });
    let revealed = 0;
    fixture.componentInstance.reveal.subscribe(() => (revealed += 1));
    el.querySelector<HTMLButtonElement>('button.alarm-chip')!.click();
    expect(revealed).toBe(1);
  });

  it('goes away when the condition clears', () => {
    const { fixture, el } = render({ kind: 'bot-down', text: 'Bot down' });
    fixture.componentRef.setInput('alarm', null);
    fixture.detectChanges();
    expect(el.querySelector('button')).toBeNull();
  });

  it('is a polite status region holding a real button, padded for touch, with no title', () => {
    const { el } = render({ kind: 'disconnected', text: 'Disconnected' });
    expect(el.getAttribute('role')).toBe('status');
    const button = el.querySelector('button')!;
    expect(button.getAttribute('type')).toBe('button');
    expect(button.classList).toContain('sb-hit');
    expect(button.hasAttribute('title')).toBe(false);
  });

  it('takes the warning tone, never the loss red, and keeps only the dot on a phone', () => {
    const source = readFileSync(join(process.cwd(), 'src/app/shell/alarm-chip.ts'), 'utf8');
    expect(source).toContain('background: var(--warn-soft);');
    expect(source).toContain('color: var(--warn);');
    expect(source).not.toMatch(/var\(--neg/);
    expect(source).toMatch(/@media \(max-width: 639px\) \{ \.text \{ display: none; \} \}/);
  });
});
