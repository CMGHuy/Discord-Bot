import { describe, expect, it } from 'vitest';

import { GuideChapter, GuideChapterSummary } from '../../api/models';
import { buildGuideSearchIndex, plainText, searchGuide, snippetFor, splitSections } from './guide-search';

const CHAPTERS: GuideChapterSummary[] = [
  { slug: 'what-it-is', title: 'What the bot is', order: 1, reviewed_for: '2.19.2',
    headings: [{ level: 2, text: 'Swing horizons', anchor: 'swing-horizons' }, { level: 3, text: 'Masked', anchor: 'masked' }] },
  { slug: 'glossary', title: 'Glossary', order: 12, reviewed_for: '2.19.2',
    headings: [{ level: 3, text: 'R multiple', anchor: 'r-multiple' }] },
];
const BODIES: Record<string, GuideChapter> = {
  'what-it-is': { slug: 'what-it-is', title: 'What the bot is', reviewed_for: '2.19.2', markdown: [
    '> **In plain words** paper trades only.', '## Swing horizons', 'Holding from days to weeks.',
    '```', '## not a heading', '```', '### Masked', 'Research only, never alerted.',
  ].join('\n') },
};

describe('plainText', () => {
  it('drops tags, comments, link targets and Markdown marks', () => {
    expect(plainText('<!-- figure:x --> **Bold** [the glossary](/insights/guide/glossary) <details>`code`</details>'))
      .toBe('Bold the glossary code');
  });

  it('is empty for empty input', () => {
    expect(plainText('')).toBe('');
  });
});

describe('splitSections', () => {
  it('splits at ##/### outside code fences, keeping the preface first', () => {
    const sections = splitSections(BODIES['what-it-is'].markdown);
    expect(sections).toHaveLength(3);
    expect(sections[0]).toBe('In plain words paper trades only.');
    expect(sections[1]).toBe('Holding from days to weeks. not a heading');
    expect(sections[2]).toBe('Research only, never alerted.');
  });

  it('does not split at #### or at a hash without a space', () => {
    expect(splitSections('a\n#### deep\n##tight')).toHaveLength(1);
  });

  it('reads Windows line endings like Unix ones', () => {
    expect(splitSections('pre\r\n## H\r\nbody')).toEqual(['pre', 'body']);
  });
});

describe('buildGuideSearchIndex', () => {
  const index = buildGuideSearchIndex(CHAPTERS, BODIES);

  it('lists each chapter, then each of its headings, in reading order', () => {
    expect(index.map((e) => [e.slug, e.anchor])).toEqual([
      ['what-it-is', null], ['what-it-is', 'swing-horizons'], ['what-it-is', 'masked'],
      ['glossary', null], ['glossary', 'r-multiple'],
    ]);
  });

  it('carries the section text of a loaded chapter and only the heading otherwise', () => {
    expect(index[0].text).toBe('What the bot is In plain words paper trades only.');
    expect(index[1].text).toBe('Swing horizons Holding from days to weeks. not a heading');
    expect(index[4].text).toBe('R multiple');
  });

  it('is empty for an empty guide', () => {
    expect(buildGuideSearchIndex([], {})).toEqual([]);
  });
});

describe('searchGuide', () => {
  const index = buildGuideSearchIndex(CHAPTERS, BODIES);

  it('finds headings before any body is loaded', () => {
    const bare = buildGuideSearchIndex(CHAPTERS, {});
    expect(searchGuide(bare, 'multiple').map((e) => e.anchor)).toEqual(['r-multiple']);
  });

  it('needs every word, ignores case and keeps document order', () => {
    expect(searchGuide(index, 'WEEKS holding').map((e) => e.anchor)).toEqual(['swing-horizons']);
    expect(searchGuide(index, 'research weeks')).toEqual([]);
  });

  it('matches the chapter title on every entry of that chapter', () => {
    expect(searchGuide(index, 'glossary multiple').map((e) => e.anchor)).toEqual(['r-multiple']);
  });

  it('returns nothing for a blank query and honours the limit', () => {
    expect(searchGuide(index, '   ')).toEqual([]);
    expect(searchGuide(index, 'i', 2)).toHaveLength(2);
  });
});

describe('snippetFor', () => {
  it('centres on the first matching word with ellipses', () => {
    const text = `${'a '.repeat(100)}target ${'b '.repeat(100)}`;
    const snippet = snippetFor(text, 'target', 40);
    expect(snippet).toContain('target');
    expect(snippet.startsWith('…')).toBe(true);
    expect(snippet.endsWith('…')).toBe(true);
  });

  it('starts at the beginning when nothing matches', () => {
    const text = `start ${'x '.repeat(100)}`;
    const snippet = snippetFor(text, 'zzz', 40);
    expect(snippet.startsWith('start')).toBe(true);
    expect(snippet.endsWith('…')).toBe(true);
  });

  it('returns short text whole', () => {
    expect(snippetFor('short text', 'zzz')).toBe('short text');
  });
});
