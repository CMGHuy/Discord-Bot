import { describe, expect, it } from 'vitest';

import { allSources, stripComments } from './testing/all-sources';

/**
 * The colour and radius gates' scope -- spec v167 §5 and amendment 3.
 * callSites() skips ui/ and testing/ and reads no .css, so a gate over it
 * proves nothing about the primitives or the stylesheets. allSources() is
 * the wider walker; these cases pin what it reaches and what it leaves out.
 */
describe("allSources(): the colour and radius gates' scope", () => {
  const names = allSources().map(({ name }) => name);

  for (const included of ['app/ui/button.ts', 'app/shell/shell.css', 'styles.css', 'index.html']) {
    it(`reaches ${included}`, () => {
      expect(names).toContain(included);
    });
  }

  it('leaves out styles/, whose two token files have their own rules', () => {
    expect(names.filter((name) => name.startsWith('styles/'))).toEqual([]);
  });

  it('leaves out every spec', () => {
    expect(names.filter((name) => name.endsWith('.spec.ts'))).toEqual([]);
  });

  it('keeps only .ts, .css and .html', () => {
    expect(names.filter((name) => !/\.(ts|css|html)$/.test(name))).toEqual([]);
  });

  it('names files relative to src/ with forward slashes, in a stable order', () => {
    expect(names.filter((name) => name.includes('\\'))).toEqual([]);
    expect(names).toEqual([...names].sort((a, b) => a.localeCompare(b)));
  });

  it('returns the raw source, comments included', () => {
    const button = allSources().find(({ name }) => name === 'app/ui/button.ts')!;
    expect(button.source).toContain('/*');
  });
});

describe('stripComments()', () => {
  it('drops a block comment and keeps the code around it', () => {
    expect(stripComments('a { color: red; /* #fff */ }')).toBe('a { color: red;  }');
  });

  it('drops a block comment that spans lines', () => {
    expect(stripComments('a {\n/* one\n   #fff two */\n}')).toBe('a {\n\n}');
  });

  it('drops an HTML comment', () => {
    expect(stripComments('<p><!-- #fff --></p>')).toBe('<p></p>');
  });

  it('drops a // line comment and keeps the line break', () => {
    expect(stripComments('const a = 1; // #fff\nconst b = 2;')).toBe('const a = 1; \nconst b = 2;');
  });

  it('keeps a URL, whose // follows a colon', () => {
    const url = "const u = 'https://bomeo-capital.com/#top';";
    expect(stripComments(url)).toBe(url);
  });
});
