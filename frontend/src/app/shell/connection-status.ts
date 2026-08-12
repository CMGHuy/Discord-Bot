import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

/** How the SPA is currently hearing about changes. */
export type StreamState = 'connecting' | 'live' | 'degraded' | 'dead';

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
    <div class="status" [title]="hint()">
      <span class="dot" [class]="state()"></span>
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
    .dot.live { background: var(--pos); animation: pulse 2s ease-out infinite; }
    .dot.degraded { background: var(--warn); }
    .dot.dead { background: var(--neg); }
    .dot.connecting { background: var(--text-faint); }
    .bot { color: var(--warn); }
    @keyframes pulse { 50% { opacity: 0.35; } }
    @media (prefers-reduced-motion: reduce) {
      .dot.live { animation: none; }
    }
  `,
})
export class ConnectionStatus {
  readonly state = input.required<StreamState>();
  /** Null until the bot has ever reported -- distinct from "offline". */
  readonly botAlive = input<boolean | null>(null);

  protected readonly label = computed(
    () => ({ connecting: 'connecting', live: 'live', degraded: 'polling', dead: 'offline' })[this.state()],
  );

  protected readonly hint = computed(
    () =>
      ({
        connecting: 'Opening the event stream…',
        live: 'Receiving changes as they happen.',
        degraded: 'Event stream unavailable — refreshing every 5 seconds instead.',
        dead: 'Not receiving updates. The admin may be down.',
      })[this.state()],
  );
}
