import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

// The state union is declared once, on the store that produces it. Three
// spellings of the same four strings across transport, store and chrome is
// how one of them quietly grows a fifth.
import { ConnectionState } from '../stores/connection.store';

/**
 * "Is what I am looking at actually current?" — answered in the shell,
 * once, for every workspace.
 *
 * Inputs rather than an injected store, on purpose: this is the one piece
 * of chrome whose whole job is to be honest about the data path, and a
 * component that renders exactly what it is given can be tested in every
 * state without standing up a stream. The shell owns the wiring.
 *
 * `degraded` is not an error state and must not read as one. It means the
 * event stream is gone and the UI has fallen back to polling, so the data
 * is still correct, just up to five seconds old. The spec's worst outcome
 * is a UI that looks live and is not -- which is why this is always
 * visible rather than appearing only when something breaks.
 */
@Component({
  selector: 'sb-connection-status',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="status" [class]="state()" [title]="hint()">
      <span class="dot" [class]="state()" [class.resting]="resting()"
            [class.bot-up]="botUp()" [class.bot-down]="botDown()"></span>
      <span class="state">{{ label() }}</span>
      @if (botAlive() === false) {
        <span class="bot">bot offline</span>
      } @else if (botHealthy() === false) {
        <span class="bot bot-failing">bot failing</span>
      }
    </div>
  `,
  styles: `
    /* Sheet 2's form: "Live" reads as a word next to the dot, not a shouted
       label -- no text-transform here, unlike the rest of the status
       cluster's chip-style copy. */
    .status {
      display: flex;
      align-items: center;
      gap: var(--space-6);
      font-size: var(--text-micro);
      letter-spacing: 0.08em;
      color: var(--text-muted);
    }
    .dot {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: var(--text-faint);
    }
    /* The blinking dot survives from the current UI; the card-flash does
       not. With push, "something changed" is continuous rather than a
       5-second event, so a flash would be a permanent flicker. */
    /* Greyscale and amber base case: connection STATE alone (connecting/
       live/degraded/dead) is not money (NG52's colour review) -- degraded
       and dead both mean the same caution (what you are reading may be
       stale) and the label is what tells them apart, not colour. */
    .dot.live { background: var(--text); animation: pulse 2s ease-out infinite; }
    /* Out of session hours the stream is still up but nothing is coming down
       it, and a pulse in that state claims activity that is not happening --
       it reads as "prices are moving" on an evening when they are not. The
       dot stays lit, because the connection genuinely is live; it just stops
       announcing traffic. Same reasoning as the reduced-motion rule below:
       the colour carries the state, the animation only ever carried the
       liveliness. */
    .dot.live.resting { animation: none; }
    .dot.degraded { background: var(--warn); }
    .dot.dead { background: var(--warn); }
    .dot.connecting { background: var(--text-faint); }
    /* Overrides the state-based background above, on direct request
       (2026-09-14) -- knowingly reintroducing the exact collision NG52
       argued against (green/red now doubles as P&L's own pair in this
       chrome). "bot-up" only applies once the stream is actually live, so
       "connecting"/"degraded" still read as caution amber, not a false
       green. Rule order matters: these come after the state rules above
       so they win at equal specificity. */
    .dot.bot-up { background: var(--pos); }
    .dot.bot-down { background: var(--neg); animation: none; }
    /* Dead is the more serious of the two, so it takes the whole label with
       it rather than relying on a 6px dot to carry the difference. */
    .status.dead { color: var(--warn); }
    .bot { color: var(--warn); }
    @keyframes pulse { 50% { opacity: 0.35; } }
    @media (prefers-reduced-motion: reduce) {
      .dot.live { animation: none; }
    }
  `,
})
export class ConnectionStatus {
  readonly state = input.required<ConnectionState>();
  /** Null until the bot has ever reported -- distinct from "offline". */
  readonly botAlive = input<boolean | null>(null);
  /** Null until the bot has ever completed a tick -- distinct from "failing".
   *  True/false only once the admin has a last_success to compare against. */
  readonly botHealthy = input<boolean | null>(null);
  /** Whether the US market is open. Three-valued for the same reason
   *  `ConnectionStore.marketActive` is: `null` means "not asked yet", and
   *  stilling the dot on a fact we do not have yet would be guessing. */
  readonly marketActive = input<boolean | null>(null);

  /** Connected, but with nothing to announce. Only an explicit `false`
   *  qualifies -- see the input's note. */
  protected readonly resting = computed(() => this.marketActive() === false);

  /** Green: the stream is live AND the bot has not reported itself down.
   *  `botAlive() === null` (never reported yet) does not count as up --
   *  only a live stream we have positive bot confirmation for does. */
  protected readonly botUp = computed(
    () => this.state() === 'live' && this.botAlive() === true,
  );
  /** Red: the bot has explicitly reported itself offline, regardless of
   *  stream state -- a dead bot behind a live stream is still down. */
  protected readonly botDown = computed(() => this.botAlive() === false);

  protected readonly label = computed(
    () => ({ connecting: 'Connecting', live: 'Live', degraded: 'Polling', dead: 'Offline' })[this.state()],
  );

  /** Always names the event stream, never the freshness of the data (D30) --
   *  that claim belongs to each panel's own `sb-freshness`. */
  protected readonly hint = computed(() => {
    if (this.state() === 'live' && this.resting()) {
      // Says why the dot went still, so a stopped pulse cannot be mistaken
      // for a stream that quietly died.
      return 'Event stream connected. The market is closed, so no changes are expected.';
    }
    return {
      connecting: 'Opening the event stream…',
      live: 'Connected to the event stream — receiving changes as they happen.',
      degraded: 'Event stream unavailable — refreshing every 5 seconds instead.',
      dead: 'Event stream disconnected — panels show their own data age.',
    }[this.state()];
  });
}
