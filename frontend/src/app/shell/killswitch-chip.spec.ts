import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it } from 'vitest';

import { KillswitchChip } from './killswitch-chip';

describe('KillswitchChip (v195 Phase 3)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection(), provideRouter([])] });
  });

  function render(on: boolean | null): HTMLElement {
    const fixture = TestBed.createComponent(KillswitchChip);
    fixture.componentRef.setInput('on', on);
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  it('renders nothing until the state is known, never a guessed "Armed"', () => {
    expect(render(null).innerHTML.replace(/<!--[\s\S]*?-->/g, '').trim()).toBe('');
  });

  it('reads Armed while trading runs, and links to Risk', () => {
    const chip = render(false).querySelector('a')!;
    expect(chip.textContent!.trim()).toBe('Armed');
    expect(chip.getAttribute('href')).toBe('/risk');
    expect(chip.classList).not.toContain('halted');
    expect(chip.getAttribute('aria-label')).toBe('Killswitch off, trading armed. Open Risk');
  });

  it('reads Halted when engaged: a word of its own, not only the loss colour', () => {
    const chip = render(true).querySelector('a')!;
    expect(chip.textContent!.trim()).toBe('Halted');
    expect(chip.classList).toContain('halted');
    expect(chip.getAttribute('href')).toBe('/risk');
    expect(chip.getAttribute('aria-label')).toBe('Killswitch on, trading halted. Open Risk');
  });

  it('pads its hit area for touch and explains itself without a title', () => {
    const chip = render(true).querySelector('a')!;
    expect(chip.classList).toContain('sb-hit');
    expect(chip.hasAttribute('title')).toBe(false);
  });
});
