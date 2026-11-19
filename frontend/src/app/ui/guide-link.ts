import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { RouterLink } from '@angular/router';

/** Where a `?` link lands: a chapter, and optionally one heading in it. */
export interface GuideTarget {
  slug: string;
  anchor: string | null;
}

/**
 * `'<slug>#<anchor>'` or `'<slug>'`. The anchor is the server's (the
 * browser never derives one); `guide-anchors.spec.ts` checks every literal
 * target in the app against the generated fixture, so a renamed heading
 * fails CI instead of leaving a link that lands at the top of a chapter.
 */
export function parseGuideTarget(target: string): GuideTarget {
  const [head, ...rest] = target.split('#');
  const slug = head.trim();
  if (slug === '') throw new Error(`Guide target "${target}" names no chapter`);
  const anchor = rest.join('#').trim();
  return { slug, anchor: anchor === '' ? null : anchor };
}

/**
 * The guide's contextual help (spec v215 § Page behaviour): a small `?`
 * beside an alert field or a metric that opens the matching guide section.
 *
 * The glyph is text-sized so it never changes the line it sits on; the
 * touch target is the shared `.sb-hit` box (44px on phone and tablet,
 * 24px on desktop), centred on the glyph and out of layout, so the row
 * keeps its height at every width (the lesson of commit 2a11a416).
 */
@Component({
  selector: 'sb-guide-link',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink],
  template: `
    <a class="guide-link sb-hit"
       [routerLink]="['/insights/guide', parsed().slug]"
       [fragment]="parsed().anchor ?? undefined"
       [attr.aria-label]="label()"
       [attr.title]="label()">?</a>
  `,
  styles: `
    :host { display: inline-flex; vertical-align: middle; }
    .guide-link {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 1.4em;
      height: 1.4em;
      border: 1px solid var(--border-strong);
      border-radius: 50%;
      color: var(--text-muted);
      font-size: var(--text-micro);
      font-weight: 600;
      line-height: 1;
      text-decoration: none;
      transition: color var(--transition), border-color var(--transition);
    }
    .guide-link:hover { color: var(--text); border-color: var(--text-muted); }
    .guide-link:focus-visible { outline: 1px solid var(--accent); outline-offset: 1px; }
  `,
})
export class GuideLinkComponent {
  /** `'<slug>#<anchor>'` or `'<slug>'`. Always a literal in templates. */
  readonly target = input.required<string>();
  /** The accessible name; the visible glyph is only "?". */
  readonly label = input<string>('Open the guide');

  protected readonly parsed = computed(() => parseGuideTarget(this.target()));
}
