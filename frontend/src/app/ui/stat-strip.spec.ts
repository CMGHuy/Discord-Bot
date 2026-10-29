import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { Component, provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { PreferencesStore } from '../stores/preferences.store';
import { MetricCard } from './metric-card';
import { StatStrip } from './stat-strip';
import { StatTile } from './stat-tile';

/**
 * v186 D3. jsdom lays nothing out, matches no @media and resolves no
 * component var() chain, so geometry and the custom-property contract are
 * asserted as SOURCE TEXT (the strip's :host, each tile's reads, the global
 * grid, the motion rule) and behaviour through the DOM: projection, the
 * inline --strip-cols / --strip-cols-md, the sb-strip-fixed class, tint and
 * thin-sample classes.
 */
const read = (path: string) => readFileSync(join(process.cwd(), path), 'utf8');
const uncomment = (css: string) => css.replace(/\/\*[\s\S]*?\*\//g, '');
const STRIP = read('src/app/ui/stat-strip.ts');
const STRIP_CSS = uncomment(STRIP.slice(STRIP.indexOf('styles:'), STRIP.indexOf('export class StatStrip')));
const TILE = read('src/app/ui/stat-tile.ts');
const CARD = read('src/app/ui/metric-card.ts');
const GLOBAL = uncomment(read('src/styles.css'));
const MOTION = uncomment(read('src/styles/motion.css'));
const hostRule = () => STRIP_CSS.match(/:host\s*\{[^}]*\}/)?.[0] ?? '';

@Component({
  imports: [StatStrip, StatTile],
  template: `
    <sb-stat-strip [cols]="cols()" [colsMd]="colsMd()">
      @for (n of tiles(); track n) {
        <sb-stat-tile [label]="'Tile ' + n" [value]="n + '%'" [sample]="sample()" />
      }
    </sb-stat-strip>
    <sb-stat-tile label="Outside" [value]="'1%'" />
  `,
})
class TileStripHost {
  readonly tiles = signal<number[]>([1, 2, 3, 4, 5]);
  readonly cols = signal<number | null>(4);
  readonly colsMd = signal(2);
  readonly sample = signal<number | null>(null);
}

@Component({
  imports: [StatStrip, MetricCard],
  template: `
    <sb-stat-strip [cols]="4">
      <sb-metric-card label="Inside" [value]="1.2" [tint]="'pos'" />
    </sb-stat-strip>
    <sb-metric-card label="Outside" [value]="1.2" [tint]="'pos'" />
  `,
})
class CardStripHost {}

function mount() {
  const f = TestBed.createComponent(TileStripHost);
  f.detectChanges();
  const el = f.nativeElement as HTMLElement;
  const strip = el.querySelector('sb-stat-strip') as HTMLElement;
  const grid = () => strip.querySelector('.sb-strip-grid') as HTMLElement;
  const tilesIn = () => [...grid().children].filter((child) => child.tagName === 'SB-STAT-TILE');
  return { f, el, strip, grid, tilesIn };
}

describe('sb-stat-strip (v186 D3)', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [
    provideZonelessChangeDetection(),
    { provide: PreferencesStore, useValue: { values: () => ({}) } },
  ] }));

  it('projects its tiles into the shared strip grid, and only its own', () => {
    const { el, grid, tilesIn } = mount();
    expect(grid()).not.toBeNull();
    expect(tilesIn()).toHaveLength(5);
    const outside = [...el.querySelectorAll('sb-stat-tile')].at(-1)!;
    expect(outside.closest('sb-stat-strip')).toBeNull();
  });

  it('pins the column counts when cols is set', () => {
    const { f, strip, grid } = mount();
    expect(strip.style.getPropertyValue('--strip-cols')).toBe('4');
    expect(strip.style.getPropertyValue('--strip-cols-md')).toBe('2');
    expect(grid().classList).toContain('sb-strip-fixed');
    f.componentInstance.colsMd.set(4);
    f.detectChanges();
    expect(strip.style.getPropertyValue('--strip-cols-md')).toBe('4');
  });

  it('falls back to the auto-fit grid when cols is not set', () => {
    const { f, strip, grid } = mount();
    f.componentInstance.cols.set(null);
    f.detectChanges();
    expect(strip.style.getPropertyValue('--strip-cols')).toBe('');
    expect(grid().classList).not.toContain('sb-strip-fixed');
  });

  it('renders nothing for an empty strip and draws no rule, surface or shadow of its own', () => {
    const { f, grid } = mount();
    f.componentInstance.tiles.set([]);
    f.detectChanges();
    expect(grid().children).toHaveLength(0);
    expect(STRIP_CSS).not.toMatch(/(?<![-\w])border(-[a-z]+)*\s*:/);
    expect(STRIP_CSS).not.toMatch(/(?<![-\w])(background|box-shadow)\s*:/);
    expect(STRIP).not.toContain('--panel-bg');
    expect(STRIP).not.toContain('::ng-deep');
  });

  it('sets the inherited properties every tile reads, and clips its own box', () => {
    const host = hostRule();
    for (const declaration of [
      '--figure-rule: 1px;',
      '--tile-bg: transparent;',
      '--tile-border: 0;',
      '--tile-radius: 0;',
      'display: block;',
      'overflow: hidden;',
      'min-width: 0;',
    ]) expect(host, declaration).toContain(declaration);
    // v195 Phase 2: no metric card is filled any more, so there is no fill to switch off.
    expect(host).not.toContain('--tile-tint-off');
    // The other half of the contract: the tiles read them (V186-3).
    for (const source of [TILE, CARD]) {
      expect(source).toContain('border-left: var(--figure-rule, 0px) solid var(--border);');
      expect(source).toContain('border-top: var(--figure-rule, 0px) solid var(--border);');
      expect(source).toContain('background: var(--tile-bg, var(--surface));');
      expect(source).toContain('border: var(--tile-border, 1px solid var(--border));');
      expect(source).toContain('border-radius: var(--tile-radius, var(--panel-radius));');
    }
  });

  it('shows no rule beside a single tile or the gap after an incomplete row', () => {
    // Start-edge rules only, the grid pulled 1px up and left, the host clipping.
    expect(STRIP_CSS).toMatch(/\.sb-strip-grid\s*\{\s*margin: -1px 0 0 -1px;\s*\}/);
    for (const source of [TILE, CARD]) {
      expect(source).not.toMatch(/border-(right|bottom):\s*var\(--figure-rule/);
    }
    const { f, tilesIn } = mount();
    expect(tilesIn()).toHaveLength(5); // 5 in 4 columns: no filler cell is added
    f.componentInstance.tiles.set([1]);
    f.detectChanges();
    expect(tilesIn()).toHaveLength(1);
  });

  it('keeps the judgement on a metric card in and out of a strip, and fills neither (v195 Phase 2)', () => {
    const f = TestBed.createComponent(CardStripHost);
    f.detectChanges();
    const [inside, outside] = [...(f.nativeElement as HTMLElement).querySelectorAll('sb-metric-card')];
    expect(inside.closest('sb-stat-strip')).not.toBeNull();
    expect(outside.closest('sb-stat-strip')).toBeNull();
    for (const card of [inside, outside]) {
      expect(card.classList).toContain('tint-pos');
      expect(card.querySelector('.value')!.classList).toContain('pos');
    }
    expect(STRIP).not.toContain('--tile-tint-off');
    expect(CARD).not.toContain('--tile-tint-off');
  });

  it('keeps both thin-sample cues on a tile inside a strip', () => {
    const { f, tilesIn } = mount();
    f.componentInstance.sample.set(7);
    f.detectChanges();
    for (const tile of tilesIn()) {
      expect(tile.querySelector('.tile')!.classList).toContain('thin');
      expect(tile.querySelector('.flag')!.textContent).toContain('thin sample');
    }
  });
});

describe('the strip grid (styles.css, v186 D3)', () => {
  const rule = (pattern: RegExp) => GLOBAL.match(pattern)?.[0] ?? '';

  it('auto-fits 140px columns by default, with no gap (the rules are the gap)', () => {
    const grid = rule(/(?:^|\n)\.sb-strip-grid\s*\{[^}]*\}/);
    expect(grid).toContain('display: grid;');
    expect(grid).toContain('gap: 0;');
    expect(grid).toContain('grid-template-columns: repeat(auto-fit, minmax(min(100%, 140px), 1fr));');
  });

  it('pins 2 columns below 640px, colsMd from 640px and cols from 1024px', () => {
    expect(rule(/(?:^|\n)\.sb-strip-grid\.sb-strip-fixed\s*\{[^}]*\}/))
      .toContain('grid-template-columns: repeat(2, minmax(0, 1fr));');
    expect(GLOBAL).toMatch(
      /@media \(min-width: 640px\) \{\s*\.sb-strip-grid\.sb-strip-fixed \{ grid-template-columns: repeat\(var\(--strip-cols-md, 2\), minmax\(0, 1fr\)\); \}\s*\}/,
    );
    expect(GLOBAL).toMatch(
      /@media \(min-width: 1024px\) \{\s*\.sb-strip-grid\.sb-strip-fixed \{ grid-template-columns: repeat\(var\(--strip-cols, 4\), minmax\(0, 1fr\)\); \}\s*\}/,
    );
  });

  it('widens a lone last tile only on a strip that asks for it', () => {
    expect(GLOBAL).toMatch(
      /\.sb-strip-grid\.sb-strip-fill > :last-child:nth-child\(4n \+ 3\)\s*\{\s*grid-column:\s*span 2;\s*\}/,
    );
    expect(STRIP).toContain('[class.sb-strip-fill]="fillLast()"');
  });

  it('comes after the elevation rules and casts nothing', () => {
    expect(GLOBAL.search(/\.sb-strip-grid\s*\{/)).toBeGreaterThan(GLOBAL.search(/\.elev-overlay\s*\{/));
    expect(GLOBAL.slice(GLOBAL.search(/\.sb-strip-grid\s*\{/))).not.toContain('box-shadow');
  });
});

/* v186 D3 cancelled the hover lift inside a strip; v195 §1.2 deleted the
 * lift, so there is nothing left to cancel. */
describe('nothing in a strip lifts (v195 §1.2)', () => {
  it('has no lift rule in motion.css and no lift token on the strip', () => {
    expect(MOTION).not.toContain('sb-lift');
    expect(STRIP).not.toContain('--panel-shadow-lift');
  });
});

/* v195 Phase 2: one KPI-strip look -- hairline-split cells inside one
 * bordered surface. Inside a panel the panel is that surface; standing
 * alone (sb-page's [page-kpis] slot) the strip frames itself. The frame is
 * a global rule, so the strip's own scoped CSS still draws nothing. */
describe('one KPI-strip look (v195 Phase 2)', () => {
  const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const globalRule = (selector: string) =>
    GLOBAL.match(new RegExp(`(?:^|\\n)${esc(selector)}\\s*\\{[^}]*\\}`))?.[0] ?? '';
  const cellRule = (source: string, selector: string) =>
    source.match(new RegExp(`(?:^|\\n)\\s*${esc(selector)}\\s*\\{[^}]*\\}`))?.[0] ?? '';
  const CELL = [
    'display: flex;',
    'flex-direction: column;',
    'gap: var(--space-4);',
    'height: 100%;',
    'box-sizing: border-box;',
    'padding: var(--space-10) var(--panel-pad);',
  ];

  it('frames a strip that stands alone as one bordered panel surface', () => {
    const frame = globalRule('sb-stat-strip');
    expect(frame).toContain('background: var(--panel-bg);');
    expect(frame).toContain('border: var(--panel-border);');
    expect(frame).toContain('border-radius: var(--panel-radius);');
    expect(frame).not.toContain('box-shadow');
  });

  it('drops the frame inside a panel, which is already the bordered surface', () => {
    const inPanel = globalRule('.sb-panel sb-stat-strip');
    expect(inPanel).toContain('background: none;');
    expect(inPanel).toContain('border: 0;');
    expect(inPanel).toContain('border-radius: 0;');
    expect(GLOBAL.search(/\n\.sb-panel sb-stat-strip\s*\{/)).toBeGreaterThan(GLOBAL.search(/\nsb-stat-strip\s*\{/));
  });

  it('lays a stat tile and a metric card out as the same cell', () => {
    const tile = cellRule(TILE, '.tile');
    const card = cellRule(CARD, '.card');
    for (const declaration of CELL) {
      expect(tile, `stat-tile ${declaration}`).toContain(declaration);
      expect(card, `metric-card ${declaration}`).toContain(declaration);
    }
  });

  it('fills no metric card: the value colour and its sign carry the valence', () => {
    expect(CARD).not.toMatch(/:host\(\.tint-(pos|neg)\) \.card/);
    expect(CARD).not.toContain('linear-gradient');
  });
});
