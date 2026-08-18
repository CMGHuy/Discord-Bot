import { ChangeDetectionStrategy, Component } from '@angular/core';

/**
 * The plan state machine, drawn -- `plan_engine.py`'s `_LEGAL_TRANSITIONS`,
 * as a picture rather than the sentence above it (dashboard.ts's own
 * "A plan moves PENDING → ACTIVE → PARTIAL → CLOSED..." paragraph).
 *
 * Static and unlabelled by data on purpose: this is the SHAPE of the
 * lifecycle, not a live count (the lifecycle strip above it already owns
 * the numbers). Five states, four transitions:
 *
 *   PENDING  --fills-->        ACTIVE
 *   PENDING  --expires-->      CANCELLED
 *   ACTIVE   --TP1 hit-->      PARTIAL
 *   ACTIVE   --stop hit-->     CLOSED     (before TP1 -- bypasses PARTIAL)
 *   PARTIAL  --TP2/trail-->    CLOSED
 *
 * CLOSED and CANCELLED are terminal -- `_LEGAL_TRANSITIONS` has no entry
 * for either, and neither does this picture.
 *
 * Colour discipline matches StatusIndicator's own rule: PENDING/ACTIVE/
 * PARTIAL are live STATES, not outcomes, so they stay the same neutral
 * surface/border as every other node. CLOSED and CANCELLED are not
 * coloured win/loss either -- CLOSED covers both, and this diagram is
 * about the shape of the lifecycle, not a trade's result.
 */
@Component({
  selector: 'sb-plan-lifecycle-diagram',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <svg
      viewBox="0 0 680 170"
      role="img"
      aria-label="Plan lifecycle: Pending fills into Active, or is cancelled if it
        expires or invalidates first. Active hits its stop and closes, or hits
        TP1 and moves to Partial. Partial closes at TP2 or its trailing stop."
    >
      <defs>
        <marker id="lc-arrow" viewBox="0 0 8 8" refX="7" refY="4"
                markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M0,0 L8,4 L0,8 Z" class="arrowhead" />
        </marker>
      </defs>

      <!-- main line: PENDING -> ACTIVE -> PARTIAL -> CLOSED -->
      <line x1="125" y1="30" x2="196" y2="30" class="edge" marker-end="url(#lc-arrow)" />
      <text x="160" y="21" class="edge-label">fills</text>

      <line x1="305" y1="30" x2="376" y2="30" class="edge" marker-end="url(#lc-arrow)" />
      <text x="340" y="21" class="edge-label">TP1 hit</text>

      <line x1="485" y1="30" x2="556" y2="30" class="edge" marker-end="url(#lc-arrow)" />
      <text x="520" y="14" class="edge-label">TP2 /</text>
      <text x="520" y="25" class="edge-label">trail stop</text>

      <!-- branch: PENDING -> CANCELLED -->
      <line x1="70" y1="48" x2="70" y2="121" class="edge" marker-end="url(#lc-arrow)" />
      <text x="83" y="88" class="edge-label" text-anchor="start">expires /</text>
      <text x="83" y="101" class="edge-label" text-anchor="start">invalidated</text>

      <!-- bypass: ACTIVE -> CLOSED, straight past PARTIAL -->
      <path d="M250,48 L250,95 L610,95 L610,48" class="edge" fill="none"
            marker-end="url(#lc-arrow)" />
      <text x="430" y="88" class="edge-label">stop hit (before TP1)</text>

      <!-- nodes -->
      <g class="node">
        <rect x="15" y="12" width="110" height="36" rx="8" />
        <text x="70" y="34">PENDING</text>
      </g>
      <g class="node">
        <rect x="195" y="12" width="110" height="36" rx="8" />
        <text x="250" y="34">ACTIVE</text>
      </g>
      <g class="node">
        <rect x="375" y="12" width="110" height="36" rx="8" />
        <text x="430" y="34">PARTIAL</text>
      </g>
      <g class="node node-terminal">
        <rect x="555" y="12" width="110" height="36" rx="8" />
        <text x="610" y="34">CLOSED</text>
      </g>
      <g class="node node-terminal">
        <rect x="15" y="122" width="110" height="36" rx="8" />
        <text x="70" y="144">CANCELLED</text>
      </g>
    </svg>
  `,
  styles: `
    :host { display: block; max-width: 680px; }
    svg { display: block; width: 100%; height: auto; overflow: visible; }

    .edge {
      fill: none;
      stroke: var(--text-faint);
      stroke-width: 1.5;
    }
    .arrowhead { fill: var(--text-faint); }

    .edge-label {
      fill: var(--text-secondary);
      font-size: var(--text-micro);
      text-anchor: middle;
    }

    .node rect {
      fill: var(--surface);
      stroke: var(--border);
      stroke-width: 1;
    }
    /* CLOSED and CANCELLED are where a plan's life ends -- a slightly
       stronger edge than the three live states, same idea as a terminal
       node in any state diagram, and still no win/loss colour (see the
       class doc comment on why). */
    .node-terminal rect { stroke: var(--border-strong); }
    .node text {
      fill: var(--text);
      font-size: var(--text-chip);
      font-weight: 600;
      text-anchor: middle;
      dominant-baseline: middle;
    }
  `,
})
export class PlanLifecycleDiagram {}
