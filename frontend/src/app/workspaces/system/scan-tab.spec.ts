import { SCAN_CONTROLS } from './scan-tab';

describe('Scan tab controls', () => {
  it('declares a floor for every control', () => {
    expect(SCAN_CONTROLS.every((c) => c.inlineFrom !== undefined)).toBe(true);
  });

  it('keeps every scan command inline -- three short buttons never need a sheet', () => {
    expect(SCAN_CONTROLS.every((c) => c.inlineFrom === 'xs')).toBe(true);
  });
});
