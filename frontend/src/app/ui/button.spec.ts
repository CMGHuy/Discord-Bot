import { TestBed } from '@angular/core/testing';
import { Component, provideZonelessChangeDetection } from '@angular/core';
import { beforeEach, describe, expect, it } from 'vitest';

import { Button, type ButtonVariant } from './button';

@Component({
  imports: [Button],
  template: `<button sb-button [variant]="variant">Label</button>`,
})
class Host {
  variant: ButtonVariant = 'secondary';
}

function render(variant: ButtonVariant): HTMLButtonElement {
  const f = TestBed.createComponent(Host);
  f.componentInstance.variant = variant;
  f.detectChanges();
  return f.nativeElement.querySelector('button')!;
}

describe('Button variants', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  for (const variant of ['primary', 'secondary', 'danger', 'ghost', 'icon',
                         'chip', 'segment', 'link'] as ButtonVariant[]) {
    it(`puts the ${variant} class on the native button`, () => {
      expect(render(variant).classList.contains(variant)).toBe(true);
    });
  }

  it('keeps the element a native button so disabled and submit still work', () => {
    const el = render('chip');
    expect(el.tagName).toBe('BUTTON');
  });
});
