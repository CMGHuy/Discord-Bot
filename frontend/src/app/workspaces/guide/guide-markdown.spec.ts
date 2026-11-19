import { SecurityContext, provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { DomSanitizer } from '@angular/platform-browser';
import { describe, expect, it, vi } from 'vitest';

import {
  applyHeadingAnchors, internalGuideUrl, renderGuideSegments, scrollToAnchor,
} from './guide-markdown';

const sanitize = (html: string): string => {
  TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  return TestBed.inject(DomSanitizer).sanitize(SecurityContext.HTML, html) ?? '';
};

describe('renderGuideSegments', () => {
  it('splits on a figure line and drops empty Markdown around it', () => {
    const segments = renderGuideSegments('Before\n\n<!-- figure:pipeline -->\n\nAfter\n');
    expect(segments.map((s) => s.kind)).toEqual(['md', 'figure', 'md']);
    expect(segments[1]).toEqual({ kind: 'figure', name: 'pipeline' });
    expect(renderGuideSegments('<!-- figure:pipeline -->')).toEqual([{ kind: 'figure', name: 'pipeline' }]);
  });

  it('reads Windows line endings the same way', () => {
    expect(renderGuideSegments('A\r\n<!-- figure:pipeline -->\r\nB').map((s) => s.kind)).toEqual(['md', 'figure', 'md']);
  });

  it('leaves a marker that is not alone on its line as Markdown', () => {
    expect(renderGuideSegments('text <!-- figure:pipeline -->').map((s) => s.kind)).toEqual(['md']);
  });

  it('renders GFM tables, the plain-words callout and Markdown inside details', () => {
    const [md] = renderGuideSegments([
      '> **In plain words** the bot finds levels.', '',
      '| Key | Days |', '|---|---|', '| 2w | 10 |', '',
      '<details><summary>Under the hood</summary>', '', 'Read **scan_run.py**.', '', '</details>',
    ].join('\n'));
    const html = md.kind === 'md' ? md.html : '';
    expect(html).toContain('<blockquote>');
    expect(html).toContain('<table>');
    expect(html).toMatch(/<details>[\s\S]*<strong>scan_run.py<\/strong>[\s\S]*<\/details>/);
  });
});

describe("Angular's sanitiser on rendered chapters", () => {
  it('keeps details and summary', () => {
    const [md] = renderGuideSegments('<details><summary>Under the hood</summary>\n\nText\n\n</details>');
    const clean = sanitize(md.kind === 'md' ? md.html : '');
    expect(clean).toContain('<details>');
    expect(clean).toContain('<summary>Under the hood</summary>');
  });

  it('strips scripts, handlers and ids, which is why anchors are applied afterwards', () => {
    const [md] = renderGuideSegments('<h2 id="x">T</h2>\n\n<img src="x" onerror="alert(1)">\n\n<script>alert(1)</script>');
    const clean = sanitize(md.kind === 'md' ? md.html : '');
    expect(clean).not.toContain('<script');
    expect(clean).not.toContain('onerror');
    expect(clean).not.toContain('id="x"');
  });
});

function container(html: string): HTMLElement {
  const host = document.createElement('article');
  host.innerHTML = html;
  return host;
}

const HEADINGS = [
  { level: 2, text: 'Swing horizons', anchor: 'swing-horizons' },
  { level: 3, text: 'Masked', anchor: 'masked' },
];

describe('applyHeadingAnchors', () => {
  it('sets ids in document order across segments and links each heading to itself', () => {
    const host = container('<div class="md"><h2>Swing horizons</h2></div><div class="fig"><h2>Not prose</h2></div>'
      + '<div class="md"><p>x</p><h3>Masked</h3></div>');
    applyHeadingAnchors(host, HEADINGS, '/insights/guide/what-it-is');
    const [h2, h3] = host.querySelectorAll<HTMLElement>('.md > h2, .md > h3');
    expect([h2.id, h3.id]).toEqual(['swing-horizons', 'masked']);
    expect(host.querySelector('.fig h2')!.id).toBe('');
    const link = h2.querySelector('a.permalink')!;
    expect(link.getAttribute('href')).toBe('/insights/guide/what-it-is#swing-horizons');
    expect(link.getAttribute('aria-label')).toBe('Link to this section: Swing horizons');
    expect(link.classList).toContain('sb-hit');
  });

  it('is idempotent and tolerates more rendered headings than the list names', () => {
    const host = container('<div class="md"><h2>A</h2><h2>B</h2><h2>C</h2></div>');
    applyHeadingAnchors(host, HEADINGS);
    applyHeadingAnchors(host, HEADINGS);
    expect(host.querySelectorAll('a.permalink')).toHaveLength(2);
    expect(host.querySelectorAll('h2')[2].id).toBe('');
  });
});

describe('scrollToAnchor', () => {
  it('scrolls the heading with that id into view and reports a miss', () => {
    const host = container('<div class="md"><h2 id="masked">M</h2></div>');
    const spy = vi.fn();
    (host.querySelector('h2') as HTMLElement).scrollIntoView = spy;
    expect(scrollToAnchor(host, 'masked')).toBe(true);
    expect(spy).toHaveBeenCalledWith({ block: 'start' });
    expect(scrollToAnchor(host, 'nope')).toBe(false);
  });
});

describe('internalGuideUrl', () => {
  it.each([
    ['#masked', 'what-it-is', '/insights/guide/what-it-is#masked'],
    ['/insights/guide/glossary#r-multiple', 'pipeline', '/insights/guide/glossary#r-multiple'],
    ['/risk', null, '/risk'],
    ['#', 'pipeline', null],
    ['#masked', null, null],
    ['//evil.example/x', 'pipeline', null],
    ['https://example.com', 'pipeline', null],
  ])('maps %s on %s to %s', (href, slug, expected) => {
    expect(internalGuideUrl(href, slug)).toBe(expected);
  });
});
