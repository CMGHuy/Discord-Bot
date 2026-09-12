import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ActivatedRoute, provideRouter } from '@angular/router';
import { describe, expect, it } from 'vitest';

import { PlannedWorkspace } from './planned-workspace';

function render(data = { planned: 'A symbol research desk', insteadLabel: 'Ticker detail', insteadLink: '/watchlist' }): ComponentFixture<PlannedWorkspace> {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection(), provideRouter([]), { provide: ActivatedRoute, useValue: { snapshot: { data } } }] });
  const fixture = TestBed.createComponent(PlannedWorkspace);
  fixture.detectChanges();
  return fixture;
}

describe('PlannedWorkspace', () => {
  it('names the planned surface, points to today’s alternative, and has no disabled action', () => {
    const element = render().nativeElement as HTMLElement;
    expect(element.textContent).toContain('A symbol research desk');
    expect(element.textContent).toContain('not built yet');
    expect(element.querySelector('a')?.getAttribute('href')).toContain('/watchlist');
    expect(element.querySelector('button[disabled]')).toBeNull();
  });
});
