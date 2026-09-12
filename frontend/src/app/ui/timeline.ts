import { ChangeDetectionStrategy, Component, TemplateRef, input } from '@angular/core';
import { NgTemplateOutlet } from '@angular/common';

export interface TimelineItem {
  /** Stable key — `<component>-<version>`. */
  id: string;
  title: string;
  /** One line under the title: component, date. */
  meta: string;
  current: boolean;
}

/**
 * A vertical rail of dated entries — spec v85 D28, used by Versions.
 *
 * An `<ol>` because the order is the meaning: without CSS this must still read
 * as newest-first. The dot is drawn with a border on the list item rather than
 * an SVG, so it scales with the type and needs no viewBox.
 *
 * Each entry's body is projected, so Versions can put provenance and telemetry
 * inside without this component learning what either is.
 */
@Component({
  selector: 'sb-timeline',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [NgTemplateOutlet],
  template: `
    <div class="timeline">
      <ol>
        @for (item of items(); track item.id) {
          <li class="entry" [class.current]="item.current">
            <div class="head">
              <span class="title">{{ item.title }}</span>
              @if (item.current) { <span class="badge">Current</span> }
            </div>
            <div class="meta">{{ item.meta }}</div>
            <div class="body">
              @if (bodyTemplate(); as body) {
                <ng-container [ngTemplateOutlet]="body" [ngTemplateOutletContext]="{ $implicit: item }" />
              } @else {
                <ng-content select="[body]" />
              }
            </div>
          </li>
        }
      </ol>
    </div>
  `,
  styles: `
    ol { list-style: none; margin: 0; padding: 0 0 0 var(--space-14); border-left: 1px solid var(--border); }
    .entry { position: relative; padding: 0 0 var(--space-14) var(--space-14); }
    .entry::before {
      content: '';
      position: absolute;
      left: calc(var(--space-14) * -1 - 5px);
      top: 4px;
      width: 9px;
      height: 9px;
      border-radius: 50%;
      border: 2px solid var(--border);
      background: var(--bg);
    }
    .entry.current::before { border-color: var(--accent); background: var(--accent); }
    .head { display: flex; align-items: center; gap: var(--space-8); }
    .title { font-size: var(--text-body); color: var(--text); font-variant-numeric: tabular-nums; }
    .badge {
      font-size: var(--text-micro);
      text-transform: uppercase;
      letter-spacing: 0.1em;
      color: var(--accent);
      border: 1px solid var(--accent);
      border-radius: var(--radius);
      padding: 0 4px;
    }
    .meta { font-size: var(--text-micro); color: var(--text-faint); }
  `,
})
export class Timeline {
  readonly items = input.required<TimelineItem[]>();
  /** An item-aware body keeps rich release cards inside the shared rail. */
  readonly bodyTemplate = input<TemplateRef<{ $implicit: TimelineItem }> | null>(null);
}
