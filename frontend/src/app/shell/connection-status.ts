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
      <span class="dot" [class]="state()" [class.resting]="resting()"></span>
      <span class="label">{{ label() }}</span>
      @if (botAlive() === false) {
        <span class="bot">bot offline</span>
      }
    </div>
  `,
  styles: `
    .status {
      display: flex;
      align-items: center;
      gap: var(--space-6);
      font-size: var(--text-micro);
      text-transform: uppercase;
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
    /* Greyscale and amber, never green or red: connection state is not
       money (NG52's colour review). Green here made "the stream is up" and
       "this position is in profit" the same colour in the same chrome, and
       red made a fallback to polling look like a loss. Live is the bright
       end of the ramp plus the pulse; degraded and dead are both amber
       because both mean the same caution — what you are reading may be
       stale — and the label is what tells them apart. */
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
  /** Whether the US market is open. Three-valued for the same reason
   *  `ConnectionStore.marketActive` is: `null` means "not asked yet", and
   *  stilling the dot on a fact we do not have yet would be guessing. */
  readonly marketActive = input<boolean | null>(null);

  /** Connected, but with nothing to announce. Only an explicit `false`
   *  qualifies -- see the input's note. */
  protected readonly resting = computed(() => this.marketActive() === false);

  protected readonly label = computed(
    () => ({ connecting: 'connecting', live: 'live', degraded: 'polling', dead: 'offline' })[this.state()],
  );

  protected readonly hint = computed(() => {
    if (this.state() === 'live' && this.resting()) {
      // Says why the dot went still, so a stopped pulse cannot be mistaken
      // for a stream that quietly died.
      return 'Connected. The market is closed, so no changes are expected.';
    }
    return {
      connecting: 'Opening the event stream…',
      live: 'Receiving changes as they happen.',
      degraded: 'Event stream unavailable — refreshing every 5 seconds instead.',
      dead: 'Not receiving updates. The admin may be down.',
    }[this.state()];
  });
}
