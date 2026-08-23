import { TestBed } from '@angular/core/testing';
import { Component, provideZonelessChangeDetection } from '@angular/core';
import { beforeEach, describe, expect, it } from 'vitest';

import { ChipRow } from './chip-row';

@Component({
  imports: [ChipRow],
  template: `<sb-chip-row><span class="a">1</span><span class="b">2</span></sb-chip-row>`,
})
class Host {}

describe('ChipRow', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('projects its chips', () => {
    const f = TestBed.createComponent(Host);
    f.detectChanges();
    const el = f.nativeElement as HTMLElement;
    expect(el.querySelector('.a')).toBeTruthy();
    expect(el.querySelector('.b')).toBeTruthy();
  });
});
