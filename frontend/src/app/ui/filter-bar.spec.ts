import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { Component, provideZonelessChangeDetection, signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';
import { FilterBar } from './filter-bar';
const SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/filter-bar.ts'), 'utf8');
@Component({ imports: [FilterBar], template: `<sb-filter-bar [activeCount]="active()" [shown]="shown()" [total]="total()" (cleared)="onCleared()"><span class="projected">control</span></sb-filter-bar>` })
class Host { readonly active = signal(0); readonly shown = signal<number | null>(null); readonly total = signal<number | null>(null); cleared = 0; onCleared(): void { this.cleared += 1; } }
describe('FilterBar (v80 D4)', () => {
  let fixture: ComponentFixture<Host>; let host: Host;
  beforeEach(() => { TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }); fixture = TestBed.createComponent(Host); host = fixture.componentInstance; fixture.detectChanges(); });
  const el = () => fixture.nativeElement as HTMLElement;
  it('says nothing when none active', () => expect(el().querySelector('.summary')).toBeNull());
  it('states active count and remaining rows', () => { host.active.set(2); host.shown.set(12); host.total.set(40); fixture.detectChanges(); expect(el().querySelector('.active')!.textContent!.replace(/\s+/g, ' ').trim()).toBe('2 active · 12 of 40'); });
  it('shows count alone without total', () => { host.active.set(2); host.shown.set(12); fixture.detectChanges(); expect(el().querySelector('.active')!.textContent!.trim()).toBe('2 active'); });
  it('clears in one click', () => { host.active.set(1); fixture.detectChanges(); [...el().querySelectorAll('button')].find((b) => b.textContent!.includes('Clear all'))!.click(); expect(host.cleared).toBe(1); });
  it('projects controls into own row', () => { expect(el().querySelector('.bar .projected')).not.toBeNull(); expect(el().querySelector('sb-control-row')).toBeNull(); });
  it('uses a narrow container grid', () => { expect(SOURCE).toMatch(/:host \{[^}]*container: filter-bar \/ inline-size/); expect(SOURCE).toMatch(/@container filter-bar \(max-width: 639px\) \{\s*\.bar \{[^}]*grid-template-columns: repeat\(2, minmax\(0, 1fr\)\)/); });
  it('deprecates filter chips', () => expect(SOURCE).toMatch(/Deprecated \(v80 D4\)[\s\S]*sb-segmented/));
});
