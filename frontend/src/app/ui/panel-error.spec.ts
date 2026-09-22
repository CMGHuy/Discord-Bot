import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { PanelError } from './panel-error';

describe('PanelError', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));
  it('names the failure and retries on click', () => {
    const fixture = TestBed.createComponent(PanelError); fixture.componentRef.setInput('message', 'The admin is not responding.');
    const retry = vi.fn(); fixture.componentInstance.retry.subscribe(retry); fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.getAttribute('role')).toBe('alert'); expect(el.textContent).toContain('Could not load'); expect(el.textContent).toContain('The admin is not responding.');
    (el.querySelector('button') as HTMLButtonElement).click(); expect(retry).toHaveBeenCalledTimes(1);
  });
});
