import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { Hint } from './hint';
import { money, num, pct, rMultiple, share } from './format';

/**
 * Entry, target and stop in one cell — spec v18 Decision 4.
 *
 * Always reads `entry → target / stop`, in that order, for both directions.
 * For a short the target is the LOWER number and the stop the higher one, so
 * the colours carry which is which, not the positions. Anything that inferred
 * role from magnitude would read correctly on every long and invert silently
 * on every short — which is the worst version of the bug, because the cell
 * still looks plausible.
 *
 * Three columns collapse into one here, so the tooltip spells the roles out:
 * the colour pair alone is not readable for everyone, and a bare `178.00 →
 * 195.00 / 170.00` does not say which number is the stop.
 *
 * v177: a PARTIAL runner with no TP2 reads on two lines (`planTp1` set) --
 * the original plan, then `Trail best → exit (peak% / exit%)` -- and a
 * closed partial trade shows the runner's exit in the target slot
 * (`runnerExit` set). The callers decide which through `runnerCellInputs`.
 */
@Component({
  selector: 'sb-plan-cell',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Hint],
  template: `
    @if (runnerMode()) {
      <span class="plan runner">
        <span class="line l1">
          <span class="entry">{{ fmt(first()) }}</span>
          <span class="sep">{{ ' → ' }}</span>
          <span class="target">{{ fmt(planTp1()) }}</span>
          <span class="sep">{{ ' / ' }}</span>
          <span class="stop">{{ fmt(planStop()) }}</span>
          <span class="sep">{{ ' (' }}</span><span class="rise">{{ fmtPct(planRisePct()) }}</span><span class="sep">{{ ' - ' }}</span><span class="drop">{{ fmtPct(planDropPct()) }}</span><span class="sep">{{ ')' }}</span>
        </span>
        @if (trail(); as t) {
          <span class="line l2">
            <span class="trail">Trail</span><span class="sep">{{ ' ' }}</span>
            <span class="best">{{ fmt(t.best) }}</span>
            <span class="sep">{{ ' → ' }}</span>
            <span class="exit">{{ fmt(t.exit) }}</span>
            <span class="sep">{{ ' (' }}</span><span class="peak" [class.loss]="t.bestPct < 0">{{ signedPct(t.bestPct) }}</span><span class="sep">{{ ' / ' }}</span><span class="lock" [class.loss]="t.exitPct < 0">{{ signedPct(t.exitPct) }}</span><span class="sep">{{ ')' }}</span>
          </span>
        }
        <sb-hint [text]="runnerHint()" label="About this runner's plan" align="left" />
      </span>
    } @else {
      <span class="plan" [title]="tooltip()">
        <span class="entry" [class.pending]="showsTrigger()">{{ fmt(first()) }}</span>
        <span class="sep">{{ ' → ' }}</span>
        <span class="target" [class.loss]="runnerLoss()">{{ targetText() }}</span>
        <span class="sep">{{ ' / ' }}</span>
        <span class="stop">{{ fmt(stop()) }}</span>
        <span class="sep">{{ ' (' }}</span><span class="rise" [class.loss]="runnerLoss()">{{ riseText() }}</span><span class="sep">{{ ' - ' }}</span><span class="drop">{{ fmtPct(dropPct()) }}</span><span class="sep">{{ ')' }}</span>
      </span>
    }
  `,
  styles: `
    /* Three prices and two separators read as one plan. The table's scroller
       preserves that run on every viewport, including the pinned phone mode. */
    .plan {
      font-family: var(--font-mono);
      font-size: var(--text-table);
      white-space: nowrap;
    }
    .entry  { color: var(--text-secondary); }
    /* A trigger is a price nothing has traded at yet. Dashed underline rather
       than a colour: the palette's hues all mean something already, and
       "provisional" is not one of them. */
    .entry.pending {
      color: var(--text-faint);
      border-bottom: 1px dashed currentColor;
    }
    .target { color: var(--pos); }
    .stop   { color: var(--neg); }
    /* Same roles as .target/.stop -- rise is the TP-side move, drop is the
       SL-side move -- so the same colour pair carries the same meaning. */
    .rise   { color: var(--pos); }
    .drop   { color: var(--neg); }
    /* v177 -- a trailing runner with no TP2 reads on two lines: the original
       plan, then the trail. Each line is its own block and never wraps, so
       the 375px no-wrap rule (dashboard.ts) holds per line; the second line
       adds height, not width. */
    .plan.runner { display: inline-block; }
    .line { display: block; white-space: nowrap; }
    /* A small muted label, so line 2 is never read as a second plan. */
    .trail { color: var(--text-faint); font-size: var(--text-micro); }
    .best  { color: var(--text-secondary); }
    .exit  { color: var(--neg); }
    .peak, .lock { color: var(--pos); }
    /* A signed figure on the loss side of the entry (a gap through the stop,
       a runner closed below its fill) keeps the loss colour with its minus. */
    .target.loss, .rise.loss, .peak.loss, .lock.loss { color: var(--neg); }
    /* Spacing lives in the TEXT, not in a margin. Angular strips whitespace
       between elements, so a margin-only gap renders correctly and leaves
       textContent as '178.00→195.00/170.00' -- which is what a screen reader
       announces and what anything reading the cell as a string gets. In a
       mono font the literal spaces are exactly one cell wide anyway.
       Literal spaces preserve the relationship in the text as well. */
    .sep    { color: var(--text-faint); white-space: pre; }
  `,
})
export class PlanCell {
  readonly entry = input<number | null>(null);
  readonly target = input<number | null>(null);
  readonly stop = input<number | null>(null);
  /**
   * The stop-entry price a plan is still waiting on — SR53.
   *
   * A PENDING plan has no `entry`: nothing has filled. Without this the cell
   * read `— → 195.00 / 170.00`, which says the two levels but not the price
   * that would put you in them, and the trigger was the actionable number the
   * old plans board led with.
   */
  readonly trigger = input<number | null>(null);

  /**
   * True once TP1 has banked and `stop`/`target` are the runner's own
   * working_stop/TP2 rather than the original plan levels. For a
   * short that working stop legitimately sits BELOW entry -- it protects
   * the profit TP1 already locked in, not the original risk -- which reads
   * as backwards (a short's stop "should" be on the far side of entry from
   * target) unless the tooltip says why.
   */
  readonly stopKind = input<'risk' | 'trailing' | 'derived_floor'>('risk');
  readonly targetIsBankedTp1 = input<boolean>(false);
  readonly floorR = input<number | null>(null);
  readonly priceR = input<number | null>(null);
  readonly headroomR = input<number | null>(null);

  /* -- v58: the banked TP1 leg, shown in the tooltip once PARTIAL -------- */

  /** Fraction of the position TP1 closed (0-1). Null until PARTIAL. */
  readonly bankedFraction = input<number | null>(null);
  /** The TP1 leg's own R-multiple. */
  readonly bankedR = input<number | null>(null);
  /** %-gain on the TP1 leg, from the position's ORIGINAL entry to the
   *  leg's own exit price -- not the same number as the R-multiple. */
  readonly bankedPct = input<number | null>(null);
  /** $-amount for the same leg. Null when size is unknown -- omitted
   *  rather than shown as zero. */
  readonly bankedAmount = input<number | null>(null);
  /** The TP1 leg's own fill price -- the runner's "entry" for display
   *  purposes, distinct from `entry` above (the original position entry). */
  readonly bankedEntry = input<number | null>(null);
  /** Needed to format `bankedAmount`; the caller's own currency symbol. */
  readonly currency = input<string | null>(null);

  /* -- v177: a trailing runner's two lines, a closed runner's exit -------- */

  /** The plan's ORIGINAL TP1. Non-null switches the cell to two lines:
   *  line 1 the original plan, line 2 the trail. */
  readonly planTp1 = input<number | null>(null);
  /** The plan's ORIGINAL stop (`risk_stop`), line 1's stop slot. */
  readonly planStop = input<number | null>(null);
  /** Best price since TP1 (or the TP1 fill until one is recorded). Line 2
   *  exits at `stop` (the live trailing stop or locked-in floor). */
  readonly trailBest = input<number | null>(null);
  /** Per-share % from the original entry at `trailBest` -- signed. */
  readonly trailBestPct = input<number | null>(null);
  /** Per-share % from the original entry if `stop` fills -- signed. */
  readonly trailExitPct = input<number | null>(null);
  /** A closed runner's actual exit price. Non-null puts it in the target
   *  slot with a signed `runnerExitPct` in the rise slot. */
  readonly runnerExit = input<number | null>(null);
  readonly runnerExitPct = input<number | null>(null);
  /** What closed the runner, a leg reason (see `runnerExitLabel`). */
  readonly runnerExitReason = input<string | null>(null);

  protected readonly runnerMode = computed(() => this.planTp1() !== null);
  protected readonly planRisePct = computed(() => this.movePct(this.planTp1()));
  protected readonly planDropPct = computed(() => this.movePct(this.planStop()));

  /** Line 2's numbers, or null when any is missing: the line is then
   *  omitted rather than drawn with a dash for a number that exists. */
  protected readonly trail = computed((): TrailLine | null => {
    const best = this.trailBest();
    const exit = this.stop();
    const bestPct = this.trailBestPct();
    const exitPct = this.trailExitPct();
    if (this.entry() === null || best === null || exit === null || bestPct === null || exitPct === null) {
      return null;
    }
    return { best, exit, bestPct, exitPct };
  });

  protected readonly planTooltip = PLAN_LINE_TOOLTIP;

  protected readonly trailTooltip = computed(() => {
    const t = this.trail();
    if (t === null) return '';
    const floor = this.stopKind() === 'derived_floor';
    const head = floor ? 'Locked-in floor' : 'Trailing stop';
    const level = floor ? 'the locked-in floor' : 'the trailing stop';
    return `${head}. Best price so far → price ${level} would exit at. `
      + `${pct(t.bestPct, 1)} is the peak since TP1 (unrealised); `
      + `${pct(t.exitPct, 1)} is the result if the stop fills at ${this.fmt(t.exit)}, `
      + 'per share from the original entry, before costs and tax. '
      + `${this.isShortRunner() ? SHORT_GAINS : LONG_GAINS} ${PAPER_LEVEL}`;
  });

  /** v194 A3: one hint for both runner lines -- what line 1 is and, when
   *  line 2 shows, what its trail figures mean. */
  protected readonly runnerHint = computed(() => {
    const trail = this.trailTooltip();
    return trail ? `${this.planTooltip} ${trail}` : this.planTooltip;
  });

  /** Direction is not an input: a short's TP1 sits below its entry. */
  private readonly isShortRunner = computed(() => {
    const tp1 = this.planTp1();
    const entry = this.entry();
    return tp1 !== null && entry !== null && tp1 < entry;
  });

  protected readonly riseText = computed(() =>
    this.runnerExit() !== null ? this.signedPct(this.runnerExitPct()) : this.fmtPct(this.risePct()),
  );

  protected readonly runnerLoss = computed(() =>
    this.runnerExit() !== null && (this.runnerExitPct() ?? 0) < 0,
  );

  /** True when the first number is a trigger rather than a fill. */
  protected readonly showsTrigger = computed(
    () => this.entry() === null && this.trigger() !== null,
  );

  protected readonly first = computed(() =>
    this.showsTrigger() ? this.trigger() : this.entry(),
  );

  /**
   * Planned %-move from entry (or trigger, if still pending) to each level --
   * the risk/reward a trader reads the entry → target/stop triple for in the
   * first place, so it belongs next to the prices rather than a click away.
   *
   * Unsigned: `target`/`stop` already carry the correct role for either
   * direction (a short's target is the lower number), so the move's
   * magnitude alone tells the story -- rise is always the TP-side distance,
   * drop always the SL-side one, regardless of which way the position runs.
   */
  protected readonly risePct = computed(() => this.movePct(this.shownTarget()));
  protected readonly dropPct = computed(() => this.movePct(this.stop()));

  /** A trailing runner with no TP2 has no live target, so the slot shows the
   *  TP point that was actually hit (the banked leg's fill) instead of a dash. */
  private readonly bankedFill = computed(() =>
    this.target() === null && this.targetIsBankedTp1() ? this.bankedEntry() : null,
  );

  private readonly shownTarget = computed(() => this.bankedFill() ?? this.target());

  protected readonly targetText = computed(() => {
    const exit = this.runnerExit();
    if (exit !== null) return this.fmt(exit);
    return this.bankedFill() !== null ? `${this.fmt(this.bankedFill())} ✓` : this.fmt(this.target());
  });

  private movePct(level: number | null): number | null {
    const base = this.first();
    if (base === null || level === null || base === 0) return null;
    return Math.abs(((level - base) / base) * 100);
  }

  protected readonly tooltip = computed(() => {
    const runnerExit = this.runnerExit();
    if (runnerExit !== null) return this.closedRunnerTooltip(runnerExit);
    // Names the role, because the styling difference alone does not: an
    // unfilled plan and a filled one are one glyph apart otherwise.
    const lead = this.showsTrigger()
      ? `Trigger ${this.fmt(this.trigger())} (not yet filled)`
      : `Entry ${this.fmt(this.entry())}`;
    const stopWord = { risk: 'Stop', trailing: 'Trailing stop', derived_floor: 'Locked-in floor' }[this.stopKind()];
    const targetPart = this.targetIsBankedTp1()
      ? `TP1 banked · floor ${formatR(this.floorR())} · price ${formatR(this.priceR())} · headroom ${formatR(this.headroomR())}`
      : `Target ${this.fmt(this.target())}`;
    let out = `${lead} · ${targetPart} · ${stopWord} ${this.fmt(this.stop())}`;
    const fraction = this.bankedFraction();
    const r = this.bankedR();
    const entry = this.bankedEntry();
    if (fraction !== null && r !== null && entry !== null) {
      const extras: string[] = [];
      const pctVal = this.bankedPct();
      if (pctVal !== null) extras.push(pct(pctVal));
      const amountVal = this.bankedAmount();
      const currencyVal = this.currency();
      if (amountVal !== null && currencyVal !== null) extras.push(money(amountVal, currencyVal));
      const extraText = extras.length ? ` (${extras.join(', ')})` : '';
      out += ` · ${share(fraction * 100)} banked ${rMultiple(r)}${extraText} @ ${this.fmt(entry)}`;
    }
    return out;
  });

  private closedRunnerTooltip(exit: number): string {
    return `Entry ${this.fmt(this.entry())} · Runner exit (${runnerExitLabel(this.runnerExitReason())}): `
      + `${this.fmt(exit)}, ${this.signedPct(this.runnerExitPct())} per share from the original entry, before costs and tax`
      + ` · Stop ${this.fmt(this.stop())}`;
  }

  protected fmt(v: number | null): string {
    return num(v);
  }

  protected fmtPct(v: number | null): string {
    return share(v, 1);
  }

  /** Signed, one decimal: a gain or loss per share, not a distance. */
  protected signedPct(v: number | null): string {
    return pct(v, 1);
  }
}

const formatR = (value: number | null): string => value === null ? '—' : `${value.toFixed(1)}R`;

interface TrailLine {
  best: number;
  exit: number;
  bestPct: number;
  exitPct: number;
}

const PLAN_LINE_TOOLTIP = 'Original plan (TP1 already filled): entry → TP1 / original stop. '
  + 'Percentages are the distance from the entry to each level. '
  + 'The stop shown is the original; the live exit is on the next line.';
const SHORT_GAINS = 'A short gains when price falls.';
const LONG_GAINS = 'A long gains when price rises.';
const PAPER_LEVEL = "The bot's paper level: your broker's resting orders are not synced, the bot does not update your broker's orders.";

const RUNNER_EXIT_LABELS: Readonly<Record<string, string>> = {
  tp1_runner_trail: 'trailing stop',
  giveback: 'give-back stop',
  tp1_runner_be: 'floor stop',
  tp1_runner_tp2: 'TP2',
  manual: 'manual close',
  tp1_runner_progress_stall: 'progress stall',
  time_exit: 'time exit',
};

/** What closed a runner, in words, for the closed cell's tooltip. The cell
 *  itself prints numbers only; an unknown leg reason reads "runner exit". */
export function runnerExitLabel(reason: string | null): string {
  return reason !== null && Object.hasOwn(RUNNER_EXIT_LABELS, reason)
    ? RUNNER_EXIT_LABELS[reason]
    : 'runner exit';
}

/** %-gain on an already-banked leg, from the position's ORIGINAL entry to
 *  that leg's own fill price, signed by direction -- the number a trader
 *  means by "how much did that leg make", not the R-multiple alone. */
export function bankedLegPct(
  entry: number | null,
  bankedEntry: number | null,
  direction: string,
): number | null {
  if (entry === null || bankedEntry === null || entry === 0) return null;
  const raw = ((bankedEntry - entry) / entry) * 100;
  return direction === 'bearish' ? -raw : raw;
}

/** $-amount for the same leg -- the ORIGINAL share count times the fraction
 *  that leg closed, times the move from entry to its own fill price. Null
 *  when any input needed to compute it is unknown. */
export function bankedLegAmount(
  entry: number | null,
  bankedEntry: number | null,
  bankedFraction: number | null,
  shares: number | null,
  direction: string,
): number | null {
  if (entry === null || bankedEntry === null || bankedFraction === null || shares === null) {
    return null;
  }
  const raw = (bankedEntry - entry) * shares * bankedFraction;
  return direction === 'bearish' ? -raw : raw;
}
