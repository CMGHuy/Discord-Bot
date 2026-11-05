import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { describe, expect, it } from 'vitest';

import { PNL_BASIS_LABEL, PnlBasis } from './pnl-basis';

@Component({ imports: [PnlBasis], template: '<sb-pnl-basis />' })
class Host {}

describe('sb-pnl-basis', () => {
  it('exports the agreed P&L basis label', () => {
    expect(PNL_BASIS_LABEL).toBe('pre-tax, before modelled frictions');
  });

  it('shows the basis below a figure', () => {
    const fixture = TestBed.createComponent(Host);
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).querySelector('.pnl-basis')?.textContent)
      .toBe('pre-tax, before modelled frictions');
  });
});
