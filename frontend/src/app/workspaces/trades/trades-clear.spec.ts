import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection, signal } from '@angular/core';
import { provideRouter } from '@angular/router';
import { patchState } from '@ngrx/signals';
import { unprotected } from '@ngrx/signals/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { authInterceptor, errorInterceptor, loadingInterceptor } from '../../api/interceptors';
import { ConnectionStore } from '../../stores/connection.store';
import { PreferencesStore } from '../../stores/preferences.store';
import { TradesStore } from '../../stores/trades.store';
import { REFUSED, RESET } from '../../stores/trades-clear.fixture';
import { installDialogPolyfill } from '../../testing/dialog-polyfill';
import { FORCE_RESET_CONSEQUENCE, Trades } from './trades';

/* v189 A6/A7 on the Trades page: the notice after a clear, the refusal with
 * an explicitly confirmed force, and the bulk-dialog wording. */

const HISTORY_URL = '/api/v1/trades/clear-history';

describe('Trades bulk-clear replies (v189)', () => {
  let fixture: ComponentFixture<Trades>;
  let backend: HttpTestingController;
  const el = () => fixture.nativeElement as HTMLElement;
  const forceDialog = () => el().querySelector('sb-confirm-dialog[data-dialog="force-reset"]')!;

  beforeEach(() => {
    installDialogPolyfill();
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        provideHttpClient(withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor])),
        provideHttpClientTesting(),
        TradesStore,
        { provide: ConnectionStore, useValue: { currency: signal('$') } },
        { provide: PreferencesStore, useValue: { values: signal({}), isLoaded: signal(true), update: () => undefined } },
      ],
    });
    fixture = TestBed.createComponent(Trades);
    fixture.detectChanges();
    backend = TestBed.inject(HttpTestingController);
  });

  const patch = (state: Record<string, unknown>) => {
    patchState(unprotected(TestBed.inject(TradesStore)), state);
    fixture.detectChanges();
  };

  it('shows the server notice under the result, in its pre-line block', () => {
    patch({ clearResult: 'Cleared 2 open positions.', clearNotice: 'Ended 1 open position(s): AAPL\nNo more stop or take-profit alerts.' });
    const notice = el().querySelector('[data-testid="clear-notice"]')!;
    expect(notice.getAttribute('role')).toBe('status');
    expect(notice.textContent).toContain('Ended 1 open position(s): AAPL');
    expect(notice.textContent).toContain('No more stop or take-profit alerts.');
    expect(notice.classList).toContain('clear-notice');           // white-space: pre-line keeps the lines
  });

  it('shows a refusal as an alert with a force button, and sends nothing by itself', () => {
    patch({ clearRefusal: REFUSED });
    const refusal = el().querySelector('[data-testid="clear-refusal"]')!;
    expect(refusal.getAttribute('role')).toBe('alert');
    expect(refusal.textContent).toContain('Reset refused: the kill switch is tripped.');
    expect(refusal.querySelector('button')!.textContent!.trim()).toBe('Reset anyway…');
    expect(el().querySelector('.command-error')).toBeNull();
    backend.expectNone((r) => r.url === HISTORY_URL);
  });

  it('forces only after its own confirmation, which says the kill switch stays on', () => {
    patch({ clearRefusal: REFUSED });
    (el().querySelector('[data-testid="clear-refusal"] button') as HTMLButtonElement).click();
    fixture.detectChanges();
    expect(forceDialog().textContent).toContain(FORCE_RESET_CONSEQUENCE);
    expect(FORCE_RESET_CONSEQUENCE).toContain('The kill switch stays on');
    backend.expectNone((r) => r.url === HISTORY_URL);

    const buttons = forceDialog().querySelectorAll('button');
    (buttons[buttons.length - 1] as HTMLButtonElement).click();
    fixture.detectChanges();
    const req = backend.expectOne((r) => r.method === 'POST' && r.url === HISTORY_URL);
    expect(req.request.body).toEqual({ force: true });
    req.flush({ ...RESET, kill_switch: true });
    fixture.detectChanges();
    expect(el().querySelector('[data-testid="clear-refusal"]')).toBeNull();
    expect(el().querySelector('.cleared')!.textContent).toContain('Archived as account-reset-20261024T101500Z.json');
  });

  it('cancelling the force dialog sends nothing and keeps the refusal on screen', () => {
    patch({ clearRefusal: REFUSED });
    (el().querySelector('[data-testid="clear-refusal"] button') as HTMLButtonElement).click();
    fixture.detectChanges();
    (forceDialog().querySelectorAll('button')[0] as HTMLButtonElement).click();
    fixture.detectChanges();
    backend.expectNone((r) => r.url === HISTORY_URL);
    expect(el().querySelector('[data-testid="clear-refusal"]')).not.toBeNull();
  });

  it('shows an archive failure as an error, with no force offered', () => {
    patch({ clearError: 'Nothing was cleared: the archive could not be written (disk full).' });
    expect(el().querySelector('.command-error')!.textContent).toContain('the archive could not be written');
    expect(el().querySelector('[data-testid="clear-refusal"]')).toBeNull();
  });
});
