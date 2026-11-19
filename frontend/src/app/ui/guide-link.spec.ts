import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { ChangeDetectionStrategy, Component, provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { describe, expect, it } from 'vitest';

import { GuideLinkComponent, parseGuideTarget } from './guide-link';

/* What earns tests here: the target string is the only contract a placement
 * has, so its parsing is pinned; the link must carry an accessible name (the
 * glyph alone is "?"); and the hit area must come from the out-of-flow
 * .sb-hit box, never from padding that would grow the row (2a11a416). */

describe('parseGuideTarget', () => {
  it.each([
    ['sizing-risk#max-stop-loss', { slug: 'sizing-risk', anchor: 'max-stop-loss' }],
    ['glossary', { slug: 'glossary', anchor: null }],
    ['glossary#', { slug: 'glossary', anchor: null }],
    ['  pipeline # scan-run ', { slug: 'pipeline', anchor: 'scan-run' }],
  ])('reads %j', (target, expected) => {
    expect(parseGuideTarget(target)).toEqual(expected);
  });

  it.each(['', '#anchor', '   '])('rejects %j, which names no chapter', (target) => {
    expect(() => parseGuideTarget(target)).toThrow(/names no chapter/);
  });
});

@Component({
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [GuideLinkComponent],
  template: `
    <p class="row">Stop cap <sb-guide-link target="sizing-risk#max-stop-loss" label="How the stop cap works" /></p>
    <p class="plain">Glossary <sb-guide-link target="glossary" /></p>
  `,
})
class Host {}

function render(): HTMLElement {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection(), provideRouter([])] });
  const fixture = TestBed.createComponent(Host);
  fixture.detectChanges();
  return fixture.nativeElement as HTMLElement;
}

describe('GuideLinkComponent', () => {
  it('links to the chapter and scrolls to the anchor', () => {
    const link = render().querySelector<HTMLAnchorElement>('.row a.guide-link')!;
    expect(link.getAttribute('href')).toBe('/insights/guide/sizing-risk#max-stop-loss');
    expect(link.textContent!.trim()).toBe('?');
  });

  it('names the link for screen readers and on hover', () => {
    const link = render().querySelector<HTMLAnchorElement>('.row a.guide-link')!;
    expect(link.getAttribute('aria-label')).toBe('How the stop cap works');
    expect(link.getAttribute('title')).toBe('How the stop cap works');
  });

  it('defaults the label and drops the fragment for a chapter-only target', () => {
    const link = render().querySelector<HTMLAnchorElement>('.plain a.guide-link')!;
    expect(link.getAttribute('href')).toBe('/insights/guide/glossary');
    expect(link.getAttribute('aria-label')).toBe('Open the guide');
  });

  it('takes its touch target from .sb-hit', () => {
    const link = render().querySelector<HTMLAnchorElement>('a.guide-link')!;
    expect(link.classList).toContain('sb-hit');
  });
});

describe('GuideLinkComponent styles (source)', () => {
  const source = readFileSync(join(process.cwd(), 'src/app/ui/guide-link.ts'), 'utf8');
  const styles = source.slice(source.indexOf('styles: `'));

  it('never grows its row: no padding, min-height or min-width on the link', () => {
    expect(styles).not.toMatch(/padding|min-height|min-width/);
  });

  it('sizes the glyph from the text, not from fixed px (the 1px hairline is exempt)', () => {
    expect(styles).not.toMatch(/\b(?!1px\b)\d+px\b/);
  });

  it('uses theme tokens only for colour', () => {
    expect(styles).not.toMatch(/#[0-9a-fA-F]{3,8}\b|rgb\(|hsl\(/);
  });
});
