import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { describe, expect, it } from 'vitest';

import { authInterceptor, errorInterceptor, loadingInterceptor } from '../../api/interceptors';
import { GateCounterfactual, ReportEnvelope } from '../../api/models';
import {
  HOLDOUT_NOTE,
  LATEST_HEADING,
  OVER_CAP_NOTE,
  PORTFOLIO_NOTE,
  R_CAPTION,
  ReportsStore,
} from '../../stores/reports.store';
import { GATES, NOT_RUN, ok } from '../../testing/report-fixtures';
import { GatesTab } from './gates-tab';

/* The fixture's live `rs` cell is WAITING at N 29 and still carries a latest
 * reading on the wire, and its live `risk_cap` cell has a verdict of record
 * (GATE EARNS) that differs from its latest reading (INCONCLUSIVE). Both are
 * there so the wrong rendering has something to show. */

function create(
  envelope: ReportEnvelope<GateCounterfactual> = ok(GATES),
): ComponentFixture<GatesTab> {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideHttpClient(withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor])),
      provideHttpClientTesting(),
      ReportsStore,
    ],
  });
  const fixture = TestBed.createComponent(GatesTab);
  TestBed.inject(ReportsStore).resolveTab('gates').subscribe();
  TestBed.inject(HttpTestingController)
    .expectOne('/api/v1/reports/gate-counterfactual').flush(envelope);
  fixture.detectChanges();
  return fixture;
}

const host = (fixture: ComponentFixture<GatesTab>): HTMLElement => fixture.nativeElement;
const text = (el: Element | null): string => el?.textContent?.replace(/\s+/g, ' ').trim() ?? '';

/** The table's body rows that are cells (not expansion rows), in order. */
const cellRows = (fixture: ComponentFixture<GatesTab>): HTMLElement[] =>
  Array.from(host(fixture).querySelectorAll<HTMLElement>('sb-data-table tbody tr'))
    .filter((tr) => !tr.classList.contains('expansion'));

const rowFor = (fixture: ComponentFixture<GatesTab>, gate: string, population: string): HTMLElement =>
  cellRows(fixture).find((tr) => new RegExp(`\\b${gate}\\b.*\\b${population}\\b`).test(text(tr)))!;

/** Open a cell's detail through the table's own expand control. */
function expand(fixture: ComponentFixture<GatesTab>, gate: string, population: string): HTMLElement {
  rowFor(fixture, gate, population).querySelector<HTMLButtonElement>('button[aria-expanded]')!.click();
  fixture.detectChanges();
  return host(fixture).querySelector<HTMLElement>(`[data-cell="${gate}:${population.toLowerCase()}"]`)!;
}

describe('GatesTab', () => {
  it('lists one row per cell, in the report order', () => {
    const fixture = create();
    expect(cellRows(fixture).length).toBe(6);
    expect(text(cellRows(fixture)[0])).toContain('rs');
    expect(text(cellRows(fixture)[5])).toContain('compression');
  });

  it('shows WAITING with N progress and nothing else below the floor', () => {
    const fixture = create();
    const waiting = rowFor(fixture, 'rs', 'Live');
    expect(text(waiting)).toContain('WAITING');
    expect(text(waiting)).toContain('N 29 / 30');
    expect(waiting.querySelector('progress')).not.toBeNull();
    // No badge, and none of the latest reading the wire still carries.
    expect(waiting.querySelector('sb-chip')).toBeNull();
    expect(text(waiting)).not.toContain('-0.30R');
    expect(text(waiting)).not.toContain('[');
    expect(text(waiting)).not.toContain('0.40');
  });

  it('shows the verdict of record as the verdict, and a different latest reading apart', () => {
    const fixture = create();
    const riskCap = rowFor(fixture, 'risk_cap', 'Live');
    expect(text(riskCap.querySelector('sb-chip'))).toBe('GATE EARNS');
    expect(text(riskCap)).toContain('fixed 2026-10-14 · N 31');
    expect(text(riskCap)).toContain('-0.08R');
    expect(text(riskCap)).toContain('[-0.31R, +0.12R]');
    expect(text(riskCap)).toContain('0.44');
    // The latest reading's own verdict word is never printed.
    expect(text(riskCap)).not.toContain('INCONCLUSIVE');
    expect(text(host(fixture))).toContain(LATEST_HEADING);
  });

  it('shows a fixed note where a gate has no TRAIN population', () => {
    const fixture = create();
    const rsTrain = rowFor(fixture, 'rs', 'TRAIN');
    expect(text(rsTrain)).toContain('no TRAIN population');
    expect(rsTrain.querySelector('sb-chip')).toBeNull();
  });

  it('puts the portfolio-state and holdout notes beside a live verdict', () => {
    const fixture = create();
    const detail = expand(fixture, 'risk_cap', 'Live');
    expect(text(detail)).toContain(PORTFOLIO_NOTE);
    expect(text(detail)).toContain(HOLDOUT_NOTE);
    expect(text(detail)).toContain('Over these trades, the gate’s blocked setups returned less than its taken ones.');
  });

  it('labels TRAIN compression in-sample', () => {
    const fixture = create();
    const detail = expand(fixture, 'compression', 'TRAIN');
    expect(text(detail)).toContain('in-sample');
    expect(text(detail)).not.toContain(PORTFOLIO_NOTE);
  });

  it('shows the dollar-risk figure and the over-cap tag on a risk_cap row', () => {
    const fixture = create();
    const detail = expand(fixture, 'risk_cap', 'Live');
    expect(text(detail)).toContain('risk_cap_exceeded');
    expect(text(detail)).toContain('$412.50');
    expect(text(detail)).toContain(`over-cap: ${OVER_CAP_NOTE}`);
    expect(text(detail)).toContain('+0.02R / 48%');
    expect(text(detail)).toContain(R_CAPTION);
  });

  it('shows the taken re-walk beside its booked realised R, and leaves a missing one blank', () => {
    const fixture = create();
    const detail = expand(fixture, 'risk_cap', 'Live');
    // taken N 52, re-walk +0.10R / 52%, booked +0.09R
    expect(text(detail)).toContain('52');
    expect(text(detail)).toContain('+0.10R / 52%');
    expect(text(detail)).toContain('+0.09R');
    const train = expand(fixture, 'compression', 'TRAIN');
    expect(text(train)).toContain('—');
  });

  it('states the BH family and that a verdict changes no gate', () => {
    const fixture = create();
    const footer = text(host(fixture).querySelector('.footer'));
    expect(footer).toContain('BH family: the five verdict cells');
    expect(footer).toContain(R_CAPTION);
    expect(footer).toContain('a change goes through its own pre-registration');
  });

  it('renders nothing of its own when the report has not run', () => {
    const fixture = create(NOT_RUN);
    expect(host(fixture).querySelector('sb-panel')).toBeNull();
  });
});
