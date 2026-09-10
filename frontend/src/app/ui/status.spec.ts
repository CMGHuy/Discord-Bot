import { readFileSync } from 'node:fs'; import { join } from 'node:path'; import { TestBed } from '@angular/core/testing'; import { provideZonelessChangeDetection } from '@angular/core'; import { beforeEach, describe, expect, it } from 'vitest'; import { Status } from './status';
const SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/status.ts'), 'utf8');
function render(status: string | null, label: string | null = null) { const f = TestBed.createComponent(Status); f.componentRef.setInput('status', status); f.componentRef.setInput('label', label); f.detectChanges(); return f.nativeElement as HTMLElement; }
const text = (e: HTMLElement) => e.textContent!.replace(/\s+/g, ' ').trim();
describe('Status (v80 D4)', () => { beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));
  for (const [status, shape, word] of [['PENDING','pending','Pending'], ['ACTIVE','active','Active'], ['PARTIAL','partial','Partial'], ['CLOSED','closed','Closed']]) it(`draws ${status}`, () => { const e = render(status); expect(e.querySelector('.status')!.classList).toContain(shape); expect(e.querySelector('.marker')).not.toBeNull(); expect(text(e)).toBe(word); });
  it('is case-insensitive, labels marker aria-hidden, and supports label override', () => { expect(render('partial').querySelector('.status')!.classList).toContain('partial'); const e = render('ACTIVE','Open'); expect(e.querySelector('.marker')!.getAttribute('aria-hidden')).toBe('true'); expect(text(e)).toBe('Open'); });
  it('uses unknown/absent safely', () => { expect(render('EXPIRED').querySelector('.marker')).toBeNull(); expect(text(render(null))).toBe('—'); });
  it('uses shape/fill rather than P&L hue', () => { expect(SOURCE).toContain('.partial .marker { background: linear-gradient(to right, currentColor 50%, transparent 50%); }'); expect(SOURCE).not.toMatch(/--pos|--neg/); });
});
