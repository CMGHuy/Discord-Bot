import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

import { styleRules } from './style-rules';

describe('styleRules (v240)', () => {
  it('reads a .css file whole, including the rules inside @media', () => {
    const css = '.a { color: red; }\n@media (max-width: 639px) {\n  .b { gap: 0; }\n}\n';
    expect(styleRules('app/shell/x.css', css)).toEqual([
      { selector: '.a', body: 'color: red;' },
      { selector: '.b', body: 'gap: 0;' },
    ]);
  });

  it("reads a .ts file's styles: literal and never its code or template", () => {
    const ts = [
      'export class X {',
      '  run() { if (this.ok) { this.go(); } }',
      '}',
      '@Component({ selector: "sb-x", template: `<p class="a">{{ v }}</p>`, styles: `',
      '    :host { display: block; }',
      '    .a { color: var(--text); }',
      '  `})',
    ].join('\n');
    expect(styleRules('app/ui/x.ts', ts)).toEqual([
      { selector: ':host', body: 'display: block;' },
      { selector: '.a', body: 'color: var(--text);' },
    ]);
  });

  it('reads every literal of a styles: array', () => {
    const ts = '@Component({ styles: [`.a { x: 1; }`, `\n  .b { y: 2; }\n`] })';
    expect(styleRules('app/ui/x.ts', ts)).toEqual([
      { selector: '.a', body: 'x: 1;' },
      { selector: '.b', body: 'y: 2;' },
    ]);
  });

  it('returns nothing for a .ts file without styles:', () => {
    expect(styleRules('app/ui/x.ts', 'export const f = () => { return { a: 1 }; };')).toEqual([]);
  });

  it('returns nothing for .html, even when it holds an inline <style>', () => {
    expect(styleRules('index.html', '<style>html, body { background: red; }</style>')).toEqual([]);
  });

  it('strips comments before reading rules', () => {
    const css = '/* .ghost { a: b; } */\n.real { c: d; } // .line { e: f; }\n';
    expect(styleRules('styles.css', css)).toEqual([{ selector: '.real', body: 'c: d;' }]);
  });

  it('neutralises an interpolation so its braces do not split a rule', () => {
    const ts = 'styles:`.label{color:var(${CHART.tick});font-size:12px}.n{gap:0}`';
    expect(styleRules('app/ui/x.ts', ts)).toEqual([
      { selector: '.label', body: 'color:var(__expr__);font-size:12px' },
      { selector: '.n', body: 'gap:0' },
    ]);
  });

  it('joins a selector list broken over lines, and drops a stray line above the selector', () => {
    expect(styleRules('a.css', '.a,\n  .b {\n  c: d;\n}')).toEqual([{ selector: '.a, .b', body: 'c: d;' }]);
    expect(styleRules('a.css', 'stray words\n.a { b: c; }')).toEqual([{ selector: '.a', body: 'b: c;' }]);
  });

  it("reads a real component: button.ts's :host rule", () => {
    const source = readFileSync(join(process.cwd(), 'src/app/ui/button.ts'), 'utf8');
    const host = styleRules('app/ui/button.ts', source).find((rule) => rule.selector === ':host');
    expect(host?.body).toContain('border-radius: var(--control-radius);');
  });
});
