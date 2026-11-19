import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { describe, expect, it } from 'vitest';

import { GuideIndex } from '../../api/models';
import { GuideStore } from '../../stores/guide.store';
import { ViewportService } from '../../ui/breakpoints';
import { GUIDE_FIGURES } from './guide-figures';
import { GuidePipelineDiagram, PIPELINE_STAGES } from './pipeline-diagram';

const LABELS = ['Watchlist', 'Price data', 'Levels from every method', 'Duplicate merge', 'Strategy signals',
  'Gates', 'Plan construction', 'Sizing and caps', 'Alert', 'Monitoring', 'Close'];

function index(slugs: string[]): GuideIndex {
  return { chapters: slugs.map((slug, i) => ({ slug, title: slug, order: i + 1, reviewed_for: '2.19.2', headings: [] })) };
}

async function render(phone: boolean, slugs: string[]): Promise<HTMLElement> {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    providers: [provideZonelessChangeDetection(), provideHttpClient(), provideHttpClientTesting(), GuideStore,
      { provide: ViewportService, useValue: { isPhone: signal(phone) } }],
  });
  const loaded = TestBed.inject(GuideStore).ensureLoaded();
  TestBed.inject(HttpTestingController).expectOne('/api/v1/guide').flush(index(slugs));
  await loaded;
  const fixture = TestBed.createComponent(GuidePipelineDiagram);
  fixture.detectChanges();
  await fixture.whenStable();
  return fixture.nativeElement as HTMLElement;
}

const text = (el: Element) => (el.textContent ?? '').replace(/\s+/g, ' ').trim();
/** An SVG box's label: its <text> lines joined (textContent would glue them). */
const boxLabel = (el: Element) => [...el.querySelectorAll('text')].map(text).join(' ');

describe('GuidePipelineDiagram', () => {
  it('lists the eleven stages of spec v215 chapter 3, in order', () => {
    expect(PIPELINE_STAGES.map((s) => s.label)).toEqual(LABELS);
    expect(PIPELINE_STAGES.map((s) => s.lines.join(' '))).toEqual(LABELS);
  });

  it('draws one SVG box per stage on tablet and desktop, no list', async () => {
    const el = await render(false, ['pipeline']);
    expect(el.querySelector('svg[role="group"]')).not.toBeNull();
    expect(el.querySelector('ol.pipeline-steps')).toBeNull();
    expect([...el.querySelectorAll('a.pipeline-node')].map(boxLabel)).toEqual(LABELS);
    expect(el.querySelectorAll('line.edge')).toHaveLength(10);
  });

  it('links no box while its chapter does not exist', async () => {
    const el = await render(false, ['what-it-is', 'pipeline', 'glossary']);
    expect(el.querySelectorAll('a.pipeline-link')).toHaveLength(0);
    expect([...el.querySelectorAll('a.pipeline-node')].every((a) => !a.hasAttribute('href'))).toBe(true);
  });

  it('links every box whose chapter exists, to that chapter', async () => {
    const el = await render(false, ['pipeline', 'levels', 'gates']);
    const links = [...el.querySelectorAll('a.pipeline-link')];
    expect(links.map(boxLabel)).toEqual(['Price data', 'Levels from every method', 'Duplicate merge', 'Gates']);
    expect(links.map((a) => a.getAttribute('href'))).toEqual([
      '/insights/guide/levels', '/insights/guide/levels', '/insights/guide/levels', '/insights/guide/gates']);
  });

  it('becomes an ordered list of real text on phones, with the same links', async () => {
    const el = await render(true, ['pipeline', 'gates']);
    expect(el.querySelector('svg')).toBeNull();
    expect([...el.querySelectorAll('ol.pipeline-steps > li')].map(text)).toEqual(LABELS);
    const links = [...el.querySelectorAll('ol.pipeline-steps a.pipeline-link')];
    expect(links.map((a) => [text(a), a.getAttribute('href')])).toEqual([['Gates', '/insights/guide/gates']]);
    expect(links.every((a) => a.classList.contains('sb-hit'))).toBe(true);
  });

  it('is registered as the pipeline figure', () => {
    expect(GUIDE_FIGURES['pipeline']).toBe(GuidePipelineDiagram);
  });

  it('colours with theme tokens only', () => {
    const src = readFileSync(join(process.cwd(), 'src/app/workspaces/guide/pipeline-diagram.ts'), 'utf-8');
    expect(src).not.toMatch(/#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(/);
  });
});
