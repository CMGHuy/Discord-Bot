import { GuideChapter, GuideChapterSummary } from '../../api/models';

/** One searchable place: a chapter (anchor null) or one heading in it. */
export interface GuideSearchEntry {
  slug: string;
  chapterTitle: string;
  anchor: string | null;
  text: string;
}

/** The backend's heading rule (V235's `extract_headings`): `##` or `###`
 *  then whitespace, outside code fences. Kept identical so section i of a
 *  body is the section under `headings[i - 1]` of the chapter index. */
const HEADING_LINE = /^#{2,3}\s/;
const FENCE = /^\s*(```|~~~)/;

/** Markdown to searchable words: no comments, tags, link targets or marks. */
export function plainText(markdown: string): string {
  return markdown
    .replace(/<!--[\s\S]*?-->/g, ' ')
    .replace(/<[^>]+>/g, ' ')
    .replace(/!?\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/[`*_>#|~]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

/** The preface, then one plain-text section per heading line. */
export function splitSections(markdown: string): string[] {
  const sections: string[][] = [[]];
  let fenced = false;
  for (const line of markdown.replace(/\r\n?/g, '\n').split('\n')) {
    if (FENCE.test(line)) fenced = !fenced;
    if (!fenced && HEADING_LINE.test(line)) sections.push([]);
    else sections[sections.length - 1].push(line);
  }
  return sections.map((lines) => plainText(lines.join('\n')));
}

/** Every chapter and heading in reading order; a heading carries its
 *  section's prose only once the chapter body is loaded. */
export function buildGuideSearchIndex(
  chapters: GuideChapterSummary[], bodies: Record<string, GuideChapter>,
): GuideSearchEntry[] {
  return chapters.flatMap((chapter) => {
    const body = bodies[chapter.slug];
    const sections = body ? splitSections(body.markdown) : [];
    const entry = (anchor: string | null, heading: string, at: number): GuideSearchEntry => ({
      slug: chapter.slug, chapterTitle: chapter.title, anchor,
      text: `${heading} ${sections[at] ?? ''}`.trim(),
    });
    return [entry(null, chapter.title, 0), ...chapter.headings.map((h, i) => entry(h.anchor, h.text, i + 1))];
  });
}

const words = (query: string): string[] => query.toLowerCase().split(/\s+/).filter((w) => w !== '');

/** Entries holding every word of the query, in document order. */
export function searchGuide(entries: GuideSearchEntry[], query: string, limit = 20): GuideSearchEntry[] {
  const needles = words(query);
  if (needles.length === 0) return [];
  return entries
    .filter((e) => {
      const haystack = `${e.chapterTitle} ${e.text}`.toLowerCase();
      return needles.every((w) => haystack.includes(w));
    })
    .slice(0, limit);
}

/** A `width`-character window around the first matching word. */
export function snippetFor(text: string, query: string, width = 120): string {
  if (text.length <= width) return text;
  const lower = text.toLowerCase();
  const hit = words(query).map((w) => lower.indexOf(w)).find((i) => i >= 0) ?? 0;
  const start = Math.max(0, Math.min(hit - Math.floor(width / 3), text.length - width));
  const body = text.slice(start, start + width).trim();
  return `${start > 0 ? '…' : ''}${body}${start + width < text.length ? '…' : ''}`;
}
