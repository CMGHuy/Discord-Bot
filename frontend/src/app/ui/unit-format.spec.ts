import { describe, expect, it } from 'vitest';
import { alwaysMoney, inUnit, unitLabel } from './unit-format';
describe('unit-format', () => { const values={r:1.25,pct:3.4,money:1240}; it('formats headline unit',()=>{expect(inUnit(values,'r','$')).toBe('+1.25R');expect(inUnit(values,'pct','$')).toBe('+3.40%');expect(inUnit(values,'money','$')).toBe('+1,240.00 $')});it('does not turn missing data into zero',()=>expect(inUnit({r:null,pct:null,money:null},'r','$')).toBe('—'));it('always offers currency when measurable',()=>{expect(alwaysMoney(values,'$')).toBe('+1,240.00 $');expect(alwaysMoney({r:1,pct:1,money:null},'$')).toBeNull()});it('labels units',()=>{expect(unitLabel('r')).toBe('R');expect(unitLabel('pct')).toBe('%');expect(unitLabel('money')).toBe('$')})});

describe('unit-format signs (v195 correction 5)', () => {
  const loss = { r: -1.25, pct: -3.4, money: -1240 };

  it('carries the true minus into every headline unit', () => {
    expect(inUnit(loss, 'r', '$')).toBe('−1.25R');
    expect(inUnit(loss, 'pct', '$')).toBe('−3.40%');
    expect(inUnit(loss, 'money', '$')).toBe('−1,240.00 $');
    expect(alwaysMoney(loss, '€')).toBe('−1,240.00 €');
  });
});
