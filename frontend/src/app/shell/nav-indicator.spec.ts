import { Component, provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { IndicatorBox, NavIndicator, indicatorBox } from './nav-indicator';

/** Pin an element's rect: jsdom lays nothing out, so every rect is zero. */
function rect(element: Element, top: number, height: number): void {
  vi.spyOn(element, 'getBoundingClientRect').mockReturnValue({
    top, height, bottom: top + height, left: 0, right: 100, width: 100, x: 0, y: top, toJSON: () => ({}),
  } as DOMRect);
}

@Component({ template: '' })
class Blank {}

@Component({
  imports: [NavIndicator],
  template: `
    <nav class="sidebar">
      <sb-nav-indicator />
      <ul class="nav"><li><a class="first">One</a></li><li><a class="second">Two</a></li></ul>
      <ul class="nav"><li><a class="third">Three</a></li></ul>
    </nav>
  `,
})
class Host {}

describe('indicatorBox (v168 §3 #6)', () => {
  afterEach(() => vi.restoreAllMocks());

  function sidebar(): HTMLElement {
    const nav = document.createElement('nav');
    nav.innerHTML = '<ul class="nav"><li><a>One</a></li><li><a class="active">Two</a></li></ul>';
    document.body.append(nav);
    return nav;
  }

  it('measures the active link against the sidebar, scroll included', () => {
    const nav = sidebar();
    rect(nav, 100, 800);
    rect(nav.querySelector('a.active')!, 260, 36);
    Object.defineProperty(nav, 'scrollTop', { value: 40, configurable: true });
    expect(indicatorBox(nav)).toEqual<IndicatorBox>({ top: 200, height: 36 });
    nav.remove();
  });

  it('is null when no link is active', () => {
    const nav = sidebar();
    nav.querySelector('a.active')!.classList.remove('active');
    expect(indicatorBox(nav)).toBeNull();
    nav.remove();
  });
});

describe('NavIndicator (v168 §3 #6)', () => {
  let originalObserver: unknown;

  beforeEach(() => {
    originalObserver = (globalThis as { ResizeObserver?: unknown }).ResizeObserver;
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([{ path: 'a', component: Blank }, { path: 'b', component: Blank }]),
      ],
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    // `'ResizeObserver' in window` is what lightweight-charts tests, so an
    // absent observer must be deleted, not left behind as `undefined`.
    if (originalObserver === undefined) delete (globalThis as { ResizeObserver?: unknown }).ResizeObserver;
    else (globalThis as { ResizeObserver?: unknown }).ResizeObserver = originalObserver;
  });

  async function mount() {
    const fixture = TestBed.createComponent(Host);
    const el = fixture.nativeElement as HTMLElement;
    const nav = el.querySelector<HTMLElement>('nav.sidebar')!;
    rect(nav, 0, 800);
    rect(el.querySelector('a.first')!, 80, 32);
    rect(el.querySelector('a.second')!, 114, 32);
    rect(el.querySelector('a.third')!, 220, 40);
    el.querySelector('a.second')!.classList.add('active');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    const bar = () => el.querySelector<HTMLElement>('sb-nav-indicator .nav-indicator')!;
    return { fixture, el, bar };
  }

  it('renders one decorative bar on the active link after first render', async () => {
    const { el, bar } = await mount();
    expect(el.querySelectorAll('.nav-indicator').length).toBe(1);
    expect(bar().getAttribute('aria-hidden')).toBe('true');
    expect(bar().style.transform).toBe('translateY(114px)');
    expect(bar().style.height).toBe('32px');
    expect(bar().classList).not.toContain('hidden');
  });

  it('follows the active link after a navigation', async () => {
    const { fixture, el, bar } = await mount();
    el.querySelector('a.second')!.classList.remove('active');
    el.querySelector('a.third')!.classList.add('active');
    await TestBed.inject(Router).navigateByUrl('/b');
    await new Promise((resolve) => setTimeout(resolve, 0));
    fixture.detectChanges();
    expect(bar().style.transform).toBe('translateY(220px)');
    expect(bar().style.height).toBe('40px');
  });

  it('hides when nothing is active', async () => {
    const { fixture, el, bar } = await mount();
    el.querySelector('a.second')!.classList.remove('active');
    await TestBed.inject(Router).navigateByUrl('/a');
    await new Promise((resolve) => setTimeout(resolve, 0));
    fixture.detectChanges();
    expect(bar().classList).toContain('hidden');
  });

  it('works without ResizeObserver (jsdom has none)', async () => {
    (globalThis as { ResizeObserver?: unknown }).ResizeObserver = undefined;
    await expect(mount()).resolves.toBeTruthy();
  });

  it('observes the sidebar, every nav list and every link, and remeasures on a resize', async () => {
    const observed: Element[] = [];
    let fire: () => void = () => undefined;
    const disconnect = vi.fn();
    class FakeObserver {
      constructor(callback: () => void) { fire = callback; }
      observe(target: Element) { observed.push(target); }
      disconnect() { disconnect(); }
    }
    vi.stubGlobal('ResizeObserver', FakeObserver);
    const { fixture, el, bar } = await mount();
    expect(observed).toEqual([
      el.querySelector('nav.sidebar'),
      ...el.querySelectorAll('.nav'),
      ...el.querySelectorAll('.nav a'),
    ]);
    rect(el.querySelector('a.second')!, 130, 36);
    fire();
    fixture.detectChanges();
    expect(bar().style.transform).toBe('translateY(130px)');
    expect(bar().style.height).toBe('36px');
    fixture.destroy();
    expect(disconnect).toHaveBeenCalledTimes(1);
  });
});
