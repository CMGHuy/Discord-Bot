import { marked } from 'marked';

import { GuideHeading } from '../../api/models';

/** A chapter body in render order: Markdown (as HTML, still unsanitised:
 *  the template binds it with [innerHTML], which runs Angular's sanitiser)
 *  or a registered figure component. */
export type GuideSegment = { kind: 'md'; html: string } | { kind: 'figure'; name: string };

/** The marker a chapter uses to place a figure, alone on its line. The
 *  backend's `chapters.FIGURE_RE` is the same pattern. */
const FIGURE_LINE = /^<!-- figure:([a-z0-9-]+) -->$/gm;

function pushMarkdown(out: GuideSegment[], text: string): void {
  if (text.trim() === '') return;
  out.push({ kind: 'md', html: marked.parse(text, { async: false, gfm: true }) });
}

export function renderGuideSegments(markdown: string): GuideSegment[] {
  const text = markdown.replace(/\r\n?/g, '\n');
  const out: GuideSegment[] = [];
  let last = 0;
  for (const match of text.matchAll(FIGURE_LINE)) {
    pushMarkdown(out, text.slice(last, match.index));
    out.push({ kind: 'figure', name: match[1] });
    last = match.index + match[0].length;
  }
  pushMarkdown(out, text.slice(last));
  return out;
}

/**
 * Angular's sanitiser drops `id`, so anchors go on after rendering: the
 * n-th `h2`/`h3` of the prose gets the n-th heading the API listed (the
 * server computes anchors; the content test keeps headings out of
 * `<details>`, so both sides count the same headings). Figures are not
 * prose and are skipped. Each heading gains a `#` permalink.
 */
export function applyHeadingAnchors(
  container: HTMLElement, headings: readonly GuideHeading[], basePath = '',
): void {
  container.querySelectorAll<HTMLElement>('.md > h2, .md > h3').forEach((element, index) => {
    const heading = headings[index];
    if (!heading) return;
    element.id = heading.anchor;
    if (element.querySelector(':scope > a.permalink')) return;
    const link = element.ownerDocument.createElement('a');
    link.className = 'permalink sb-hit';
    link.setAttribute('href', `${basePath}#${heading.anchor}`);
    link.setAttribute('aria-label', `Link to this section: ${heading.text}`);
    link.textContent = '#';
    element.append(link);
  });
}

export function scrollToAnchor(container: HTMLElement, anchor: string): boolean {
  const target = [...container.querySelectorAll<HTMLElement>('[id]')].find((el) => el.id === anchor);
  if (!target) return false;
  target.scrollIntoView?.({ block: 'start' });
  return true;
}

/** A link inside a chapter that the router should handle, as a router URL;
 *  null for anything the browser should follow itself (other sites). */
export function internalGuideUrl(href: string, slug: string | null): string | null {
  if (href.startsWith('#')) return slug && href.length > 1 ? `/insights/guide/${slug}${href}` : null;
  if (href.startsWith('/') && !href.startsWith('//')) return href;
  return null;
}
