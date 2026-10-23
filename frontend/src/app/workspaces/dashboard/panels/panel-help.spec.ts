import { describe, expect, it } from 'vitest';

import { KPI_HELP, PANEL_HELP } from './panel-help';

describe('dashboard tooltip copy', () => {
  const all = [...Object.entries(PANEL_HELP), ...Object.entries(KPI_HELP)];

  it('covers every panel and every KPI card on the page', () => {
    expect(Object.keys(PANEL_HELP).sort()).toEqual([
      'exposureByHorizon', 'marketMovers', 'openPositions', 'realizedPnl', 'recentActivity',
      'tradingPerformance', 'watchlist',
    ]);
    expect(Object.keys(KPI_HELP).sort()).toEqual([
      'avgConfidence', 'expectancy', 'openPnl', 'openTrades', 'payoffRatio', 'realized', 'winRate',
    ]);
  });

  it('says something real and ends like a sentence', () => {
    for (const [key, text] of all) {
      expect(text.length, key).toBeGreaterThan(25);
      expect(text, key).toMatch(/[.)]$/);
    }
  });

  it('defines the payoff ratio in plain words, with an example', () => {
    expect(KPI_HELP.payoffRatio).toContain('average winning trade divided by the average losing trade');
    expect(KPI_HELP.payoffRatio).toContain('2.0');
  });

  it('keeps the two realised figures pointing at each other', () => {
    expect(KPI_HELP.realized).toContain('Realised P&L panel');
    expect(PANEL_HELP.realizedPnl).toContain('Today');
  });
});
