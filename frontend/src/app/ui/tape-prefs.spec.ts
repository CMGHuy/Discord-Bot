import { readTapeSymbols, toggleTapeSymbol, writeTapeSymbols } from './tape-prefs';

describe('tape-prefs', () => {
  it('reads an empty list when the key is absent', () => {
    expect(readTapeSymbols({})).toEqual([]);
  });

  it('reads stored symbols', () => {
    expect(readTapeSymbols({ 'tape.symbols': ['NVDA', 'AMD'] })).toEqual(['NVDA', 'AMD']);
  });

  it('tolerates a hand-edited non-array value', () => {
    expect(readTapeSymbols({ 'tape.symbols': 'NVDA' })).toEqual([]);
  });

  it('drops non-string and blank entries', () => {
    expect(readTapeSymbols({ 'tape.symbols': ['NVDA', 3, '', null] })).toEqual(['NVDA']);
  });

  it('uppercases and dedupes on read', () => {
    expect(readTapeSymbols({ 'tape.symbols': ['nvda', 'NVDA'] })).toEqual(['NVDA']);
  });

  it('toggles a symbol on and off without touching other keys', () => {
    const on = toggleTapeSymbol({ 'shell.sidebar': 'rail' }, 'nvda');
    expect(on['tape.symbols']).toEqual(['NVDA']);
    expect(on['shell.sidebar']).toBe('rail');
    expect(toggleTapeSymbol(on, 'NVDA')['tape.symbols']).toEqual([]);
  });

  it('writes a normalised list', () => {
    expect(writeTapeSymbols({}, ['amd', 'AMD', ' '])['tape.symbols']).toEqual(['AMD']);
  });
});
