import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { beforeEach, describe, expect, it } from 'vitest';

import { PlanCell, bankedLegAmount, bankedLegPct, runnerExitLabel } from './plan-cell';

function render(entry: number | null, target: number | null, stop: number | null) {
  const f = TestBed.createComponent(PlanCell);
  f.componentRef.setInput('entry', entry);
  f.componentRef.setInput('target', target);
  f.componentRef.setInput('stop', stop);
  f.detectChanges();
  return f.nativeElement as HTMLElement;
}

describe('PlanCell', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('reads entry -> target / stop for a long', () => {
    expect(render(178, 195, 170).textContent!.replace(/\s+/g, ' ').trim())
      .toBe('178.00 → 195.00 / 170.00 (9.6% - 4.5%)');
  });

  it('reads the same way for a short, where the target is the lower number', () => {
    expect(render(178, 162, 186).textContent!.replace(/\s+/g, ' ').trim())
      .toBe('178.00 → 162.00 / 186.00 (9.0% - 4.5%)');
  });

  it('colours target and stop by role, not by which is larger', () => {
    // The regression this guards: inferring role from magnitude reads
    // correctly on every long and inverts on every short.
    const el = render(178, 162, 186);
    expect(el.querySelector('.target')!.textContent!.trim()).toBe('162.00');
    expect(el.querySelector('.stop')!.textContent!.trim()).toBe('186.00');
  });

  it('renders an em dash for a missing level rather than NaN', () => {
    expect(render(178, null, 170).textContent).toContain('—');
  });

  /* -- the planned rise%/drop% pair -------------------------------------- */

  it('shows the planned rise and drop as unsigned magnitudes', () => {
    const el = render(178, 195, 170);
    expect(el.querySelector('.rise')!.textContent!.trim()).toBe('9.6%');
    expect(el.querySelector('.drop')!.textContent!.trim()).toBe('4.5%');
  });

  it('reads the same magnitudes for a short, where target/stop already carry the role', () => {
    const el = render(178, 162, 186);
    expect(el.querySelector('.rise')!.textContent!.trim()).toBe('9.0%');
    expect(el.querySelector('.drop')!.textContent!.trim()).toBe('4.5%');
  });

  it('shows an em dash for either side when a level is missing', () => {
    const el = render(178, null, 170);
    expect(el.querySelector('.rise')!.textContent!.trim()).toBe('—');
    expect(el.querySelector('.drop')!.textContent!.trim()).toBe('4.5%');
  });

  it('carries the spelled-out tooltip', () => {
    expect(render(178, 195, 170).querySelector('[title]')!.getAttribute('title'))
      .toBe('Entry 178.00 · Target 195.00 · Stop 170.00');
  });

  /* -- SR53: the trigger fallback -------------------------------------- */

  function renderWithTrigger(entry: number | null, trigger: number | null) {
    const f = TestBed.createComponent(PlanCell);
    f.componentRef.setInput('entry', entry);
    f.componentRef.setInput('target', 195);
    f.componentRef.setInput('stop', 170);
    f.componentRef.setInput('trigger', trigger);
    f.detectChanges();
    return f.nativeElement as HTMLElement;
  }

  it('shows the trigger when nothing has filled yet', () => {
    // A PENDING plan has no entry. Without this the cell read
    // "— → 195.00 / 170.00": both levels, and no price that would put you in
    // them, which is the number the old plans board led with.
    const el = renderWithTrigger(null, 176.5);
    expect(el.textContent!.replace(/\s+/g, ' ').trim())
      .toBe('176.50 → 195.00 / 170.00 (10.5% - 3.7%)');
  });

  it('says in the tooltip that the first number is a trigger', () => {
    // The dashed styling alone does not distinguish a waiting plan from a
    // filled one, and a trigger read as a fill is a position you think you
    // have and do not.
    expect(renderWithTrigger(null, 176.5).querySelector('[title]')!.getAttribute('title'))
      .toBe('Trigger 176.50 (not yet filled) · Target 195.00 · Stop 170.00');
  });

  it('marks the trigger as provisional', () => {
    expect(renderWithTrigger(null, 176.5).querySelector('.entry')!.classList
      .contains('pending')).toBe(true);
  });

  it('prefers the fill once there is one', () => {
    // Both are present on a filled plan: the trigger is history at that point,
    // and the entry is what the position actually cost.
    const el = renderWithTrigger(178, 176.5);
    expect(el.querySelector('.entry')!.textContent!.trim()).toBe('178.00');
    expect(el.querySelector('.entry')!.classList.contains('pending')).toBe(false);
  });

  it('still reads an em dash when there is neither', () => {
    const el = renderWithTrigger(null, null);
    expect(el.querySelector('.entry')!.textContent!.trim()).toBe('—');
    expect(el.querySelector('.entry')!.classList.contains('pending')).toBe(false);
  });

  /* -- the trailing-stop tooltip ---------------------------------------- */

  it('says "Trailing stop" once TP1 has banked, not plain "Stop"', () => {
    // A PARTIAL short's stop legitimately sits BELOW entry (it protects the
    // profit TP1 already locked in, not the original risk) -- which reads
    // as backwards unless the tooltip says why.
    const f = TestBed.createComponent(PlanCell);
    f.componentRef.setInput('entry', 71.64);
    f.componentRef.setInput('target', null);
    f.componentRef.setInput('stop', 69.85);
    f.componentRef.setInput('stopKind', 'trailing');
    f.detectChanges();
    expect(f.nativeElement.querySelector('[title]').getAttribute('title'))
      .toBe('Entry 71.64 · Target — · Trailing stop 69.85');
  });

  it('shows the banked TP1 fill in the target slot of a trailing runner', () => {
    // A runner with no TP2 has no live target; the slot reads as the TP point
    // that was actually hit rather than an empty dash.
    const f = TestBed.createComponent(PlanCell);
    f.componentRef.setInput('entry', 60.67);
    f.componentRef.setInput('target', null);
    f.componentRef.setInput('stop', 59.11);
    f.componentRef.setInput('stopKind', 'trailing');
    f.componentRef.setInput('targetIsBankedTp1', true);
    f.componentRef.setInput('bankedEntry', 53.94);
    f.detectChanges();
    const target = f.nativeElement.querySelector('.target');
    expect(target.textContent.trim()).toBe('53.94 ✓');
    expect(f.nativeElement.querySelector('.rise').textContent.trim()).toBe('11.1%');
  });

  it('says plain "Stop" when not trailing (the default)', () => {
    expect(render(178, 195, 170).querySelector('[title]')!.getAttribute('title'))
      .toBe('Entry 178.00 · Target 195.00 · Stop 170.00');
  });

  /* -- v58: the banked-leg tooltip clause -------------------------------- */

  function renderPartial(overrides: Partial<{
    bankedFraction: number | null; bankedR: number | null;
    bankedPct: number | null; bankedAmount: number | null;
    bankedEntry: number | null; currency: string | null;
  }> = {}) {
    const f = TestBed.createComponent(PlanCell);
    f.componentRef.setInput('entry', 51.0);
    f.componentRef.setInput('target', 150.0);
    f.componentRef.setInput('stop', 118.67);
    f.componentRef.setInput('stopKind', 'trailing');
    f.componentRef.setInput('bankedFraction', 'bankedFraction' in overrides ? overrides.bankedFraction : 0.5);
    f.componentRef.setInput('bankedR', 'bankedR' in overrides ? overrides.bankedR : 0.85);
    f.componentRef.setInput('bankedPct', 'bankedPct' in overrides ? overrides.bankedPct : 4.1);
    f.componentRef.setInput('bankedAmount', 'bankedAmount' in overrides ? overrides.bankedAmount : 42.0);
    f.componentRef.setInput('bankedEntry', 'bankedEntry' in overrides ? overrides.bankedEntry : 102.0);
    f.componentRef.setInput('currency', 'currency' in overrides ? overrides.currency : '$');
    f.detectChanges();
    return f.nativeElement as HTMLElement;
  }

  it('appends the banked leg to the tooltip once PARTIAL', () => {
    expect(renderPartial().querySelector('[title]')!.getAttribute('title')).toBe(
      'Entry 51.00 · Target 150.00 · Trailing stop 118.67 · '
      + '50% banked +0.85R (+4.10%, +42.00 $) @ 102.00',
    );
  });

  it('omits the dollar figure when amount or currency is unknown', () => {
    expect(renderPartial({ bankedAmount: null }).querySelector('[title]')!.getAttribute('title'))
      .toBe('Entry 51.00 · Target 150.00 · Trailing stop 118.67 · '
        + '50% banked +0.85R (+4.10%) @ 102.00');
  });

  it('omits the whole banked clause when nothing has banked yet', () => {
    const f = TestBed.createComponent(PlanCell);
    f.componentRef.setInput('entry', 178);
    f.componentRef.setInput('target', 195);
    f.componentRef.setInput('stop', 170);
    f.componentRef.setInput('stopKind', 'trailing');
    f.detectChanges();
    expect(f.nativeElement.querySelector('[title]').getAttribute('title'))
      .toBe('Entry 178.00 · Target 195.00 · Trailing stop 170.00');
  });
  it('says "Locked-in floor" for a derived floor stop', () => {
    const f = TestBed.createComponent(PlanCell);
    f.componentRef.setInput('entry', 121.0);
    f.componentRef.setInput('target', 140.0);
    f.componentRef.setInput('stop', 113.33);
    f.componentRef.setInput('stopKind', 'derived_floor');
    f.detectChanges();
    expect(f.nativeElement.querySelector('[title]').getAttribute('title'))
      .toBe('Entry 121.00 · Target 140.00 · Locked-in floor 113.33');
  });

  it('reports the trail rather than an absent target when TP1 is banked', () => {
    const f = TestBed.createComponent(PlanCell);
    f.componentRef.setInput('entry', 121.0);
    f.componentRef.setInput('target', null);
    f.componentRef.setInput('stop', 113.33);
    f.componentRef.setInput('stopKind', 'trailing');
    f.componentRef.setInput('targetIsBankedTp1', true);
    f.componentRef.setInput('floorR', 1.33);
    f.componentRef.setInput('priceR', 2.5);
    f.componentRef.setInput('headroomR', 1.17);
    f.detectChanges();
    expect(f.nativeElement.querySelector('[title]').getAttribute('title'))
      .toBe('Entry 121.00 · TP1 banked · floor 1.3R · price 2.5R · headroom 1.2R · Trailing stop 113.33');
  });

  it('shows an em dash for unavailable trail R values', () => {
    const f = TestBed.createComponent(PlanCell);
    f.componentRef.setInput('entry', 121.0);
    f.componentRef.setInput('target', null);
    f.componentRef.setInput('stop', 113.33);
    f.componentRef.setInput('stopKind', 'trailing');
    f.componentRef.setInput('targetIsBankedTp1', true);
    f.componentRef.setInput('floorR', 1.33);
    f.detectChanges();
    expect(f.nativeElement.querySelector('[title]').getAttribute('title'))
      .toContain('floor 1.3R · price — · headroom —');
  });
});

describe('bankedLegPct / bankedLegAmount', () => {
  it('signs pct positive for a long that gained', () => {
    expect(bankedLegPct(100, 110, 'bullish')).toBe(10);
  });

  it('signs pct positive for a short that gained (price fell)', () => {
    expect(bankedLegPct(100, 90, 'bearish')).toBe(10);
  });

  it('is null when either price is unknown', () => {
    expect(bankedLegPct(null, 110, 'bullish')).toBeNull();
    expect(bankedLegPct(100, null, 'bullish')).toBeNull();
  });

  it('computes the dollar amount from shares and fraction', () => {
    expect(bankedLegAmount(100, 110, 0.5, 100, 'bullish')).toBe(500);
  });

  it('signs the dollar amount for a short', () => {
    expect(bankedLegAmount(100, 90, 0.5, 100, 'bearish')).toBe(500);
  });

  it('is null when shares are unknown', () => {
    expect(bankedLegAmount(100, 110, 0.5, null, 'bullish')).toBeNull();
  });
});

/* -- v177: the runner's two-line cell and the closed runner's exit ------- */

function renderWith(inputs: Record<string, unknown>): HTMLElement {
  const f = TestBed.createComponent(PlanCell);
  for (const [key, value] of Object.entries(inputs)) f.componentRef.setInput(key, value);
  f.detectChanges();
  return f.nativeElement as HTMLElement;
}

const text = (el: Element | null): string => el!.textContent!.replace(/\s+/g, ' ').trim();

const hintText = (el: Element): string =>
  el.querySelector('.plan.runner sb-hint [role="tooltip"]')!.textContent!.replace(/\s+/g, ' ').trim();

/** The live RKLB short: TP1 banked at 58.33, the stop trailing at 52.437
 *  behind a best price of 49.94. Today's inputs plus the v177 ones. */
const RKLB_RUNNER = {
  entry: 60.67, target: null, stop: 52.437, stopKind: 'trailing',
  targetIsBankedTp1: true, bankedEntry: 58.33,
  planTp1: 58.33, planStop: 61.85,
  trailBest: 49.94, trailBestPct: 17.69, trailExitPct: 13.57,
};

const LONG_RUNNER = {
  entry: 100, target: null, stop: 113.3333333, stopKind: 'trailing',
  targetIsBankedTp1: true, bankedEntry: 121,
  planTp1: 120, planStop: 90,
  trailBest: 130, trailBestPct: 30, trailExitPct: 13.33,
};

const PAPER_LEVEL = "The bot's paper level: your broker's resting orders are not synced, the bot does not update your broker's orders.";

describe('PlanCell runner (two lines)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('reads the original plan on line 1 for the RKLB short', () => {
    expect(text(renderWith(RKLB_RUNNER).querySelector('.line.l1')))
      .toBe('60.67 → 58.33 / 61.85 (3.9% - 1.9%)');
  });

  it('reads best price -> trailing stop with signed per-share gains on line 2', () => {
    expect(text(renderWith(RKLB_RUNNER).querySelector('.line.l2')))
      .toBe('Trail 49.94 → 52.44 (+17.7% / +13.6%)');
  });

  it('leads line 2 with the muted Trail label', () => {
    expect(text(renderWith(RKLB_RUNNER).querySelector('.l2 .trail'))).toBe('Trail');
  });

  it('explains both runner lines in one hint, with no native titles', () => {
    const el = renderWith(RKLB_RUNNER);
    expect(el.querySelector('.plan.runner [title]')).toBeNull();
    expect(el.querySelector('.plan.runner')!.hasAttribute('title')).toBe(false);
    expect(el.querySelectorAll('.plan.runner sb-hint')).toHaveLength(1);
  });

  it('explains line 1 as the original plan', () => {
    expect(hintText(renderWith(RKLB_RUNNER)).startsWith(
      'Original plan (TP1 already filled): entry → TP1 / original stop. '
      + 'Percentages are the distance from the entry to each level. '
      + 'The stop shown is the original; the live exit is on the next line.')).toBe(true);
  });

  it('explains line 2: unrealised peak, per share, before costs, paper level', () => {
    expect(hintText(renderWith(RKLB_RUNNER))).toContain(
      'Trailing stop. Best price so far → price the trailing stop would exit at. '
      + '+17.7% is the peak since TP1 (unrealised); +13.6% is the result if the stop '
      + 'fills at 52.44, per share from the original entry, before costs and tax. '
      + `A short gains when price falls. ${PAPER_LEVEL}`);
  });

  it('reads a long runner the same way, with the long sentence', () => {
    const el = renderWith(LONG_RUNNER);
    expect(text(el.querySelector('.l1'))).toBe('100.00 → 120.00 / 90.00 (20.0% - 10.0%)');
    expect(text(el.querySelector('.l2'))).toBe('Trail 130.00 → 113.33 (+30.0% / +13.3%)');
    expect(hintText(el)).toContain('A long gains when price rises.');
  });

  it('names a derived floor "Locked-in floor" in the hint', () => {
    const hint = hintText(renderWith({ ...RKLB_RUNNER, stopKind: 'derived_floor' }));
    expect(hint).toContain('Locked-in floor. Best price so far → price the locked-in floor would exit at. ');
    expect(hint).toContain('is the result if the stop fills at 52.44');
  });

  it('keeps an explicit minus on the loss side of line 2', () => {
    const el = renderWith({ ...RKLB_RUNNER, trailExitPct: -2.5 });
    expect(text(el.querySelector('.l2'))).toBe('Trail 49.94 → 52.44 (+17.7% / -2.5%)');
    expect(el.querySelector('.l2 .lock')!.classList).toContain('loss');
    expect(el.querySelector('.l2 .peak')!.classList).not.toContain('loss');
  });

  it('shows line 1 alone when a line 2 number is missing, never a dash', () => {
    for (const missing of ['trailBest', 'trailBestPct', 'trailExitPct', 'stop']) {
      const el = renderWith({ ...RKLB_RUNNER, [missing]: null });
      expect(el.querySelector('.l1')).not.toBeNull();
      expect(el.querySelector('.l2')).toBeNull();
    }
  });

  it('never prints TP2', () => {
    expect(renderWith(RKLB_RUNNER).textContent).not.toContain('TP2');
  });

  it('stays a single legacy line when planTp1 is not set', () => {
    const el = renderWith({ ...RKLB_RUNNER, planTp1: null });
    expect(el.querySelector('.runner')).toBeNull();
    expect(el.querySelector('.line')).toBeNull();
    expect(text(el)).toBe('60.67 → 58.33 ✓ / 52.44 (3.9% - 13.6%)');
  });
});

describe('PlanCell closed runner', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  const RKLB_CLOSED = {
    entry: 60.67, target: 58.33, stop: 61.85,
    runnerExit: 52.44, runnerExitPct: bankedLegPct(60.67, 52.44, 'bearish'),
    runnerExitReason: 'tp1_runner_trail',
  };

  it('shows the runner exit in the target slot with a signed gain', () => {
    const el = renderWith(RKLB_CLOSED);
    expect(text(el)).toBe('60.67 → 52.44 / 61.85 (+13.6% - 1.9%)');
    expect(el.querySelector('.runner')).toBeNull();
  });

  it('names what closed the runner in the tooltip', () => {
    expect(renderWith(RKLB_CLOSED).querySelector('[title]')!.getAttribute('title')).toBe(
      'Entry 60.67 · Runner exit (trailing stop): 52.44, +13.6% per share from the original entry, before costs and tax · Stop 61.85');
  });

  it('reads a give-back close as such', () => {
    const title = renderWith({ ...RKLB_CLOSED, runnerExitReason: 'giveback' })
      .querySelector('[title]')!.getAttribute('title')!;
    expect(title).toContain('Runner exit (give-back stop): 52.44');
  });

  it('signs and colours a runner exit on the loss side of the entry', () => {
    const el = renderWith({ entry: 100, target: 120, stop: 90,
      runnerExit: 97, runnerExitPct: -3, runnerExitReason: 'tp1_runner_be' });
    expect(text(el)).toBe('100.00 → 97.00 / 90.00 (-3.0% - 10.0%)');
    expect(el.querySelector('.rise')!.classList).toContain('loss');
    expect(el.querySelector('.target')!.classList).toContain('loss');
  });

  it('never prints TP2, even when TP2 closed the runner', () => {
    expect(renderWith({ ...RKLB_CLOSED, runnerExitReason: 'tp1_runner_tp2' }).textContent)
      .not.toContain('TP2');
  });

  it('adds no loss class to the legacy cell', () => {
    const el = renderWith({ entry: 178, target: 195, stop: 170 });
    expect(el.querySelector('.target')!.classList).not.toContain('loss');
    expect(el.querySelector('.rise')!.classList).not.toContain('loss');
  });
});

describe('runnerExitLabel', () => {
  it('names every known runner close', () => {
    expect(runnerExitLabel('tp1_runner_trail')).toBe('trailing stop');
    expect(runnerExitLabel('giveback')).toBe('give-back stop');
    expect(runnerExitLabel('tp1_runner_be')).toBe('floor stop');
    expect(runnerExitLabel('tp1_runner_tp2')).toBe('TP2');
    expect(runnerExitLabel('manual')).toBe('manual close');
    expect(runnerExitLabel('tp1_runner_progress_stall')).toBe('progress stall');
    expect(runnerExitLabel('time_exit')).toBe('time exit');
  });

  it('falls back to "runner exit" for anything else', () => {
    expect(runnerExitLabel(null)).toBe('runner exit');
    expect(runnerExitLabel('something_new')).toBe('runner exit');
    expect(runnerExitLabel('constructor')).toBe('runner exit');
  });
});
