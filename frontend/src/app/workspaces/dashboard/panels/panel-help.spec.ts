import { describe, expect, it } from 'vitest';

import { PERFORMANCE_CAVEAT } from '../../../ui/stat-tile';
import { KPI_HELP, PANEL_HELP } from './panel-help';

describe('dashboard tooltip copy', () => {
  const all = [...Object.entries(PANEL_HELP), ...Object.entries(KPI_HELP)];

  it('covers every panel and every KPI card on the page', () => {
    expect(Object.keys(PANEL_HELP).sort()).toEqual([
      'exposureByHorizon', 'marketMovers', 'openPositions', 'recentActivity',
      'tradingPerformance', 'watchlist',
    ]);
    expect(Object.keys(KPI_HELP).sort()).toEqual([
      'avgConfidence', 'expectancy', 'openPnl', 'openTrades', 'payoffRatio', 'realized', 'realizedToday',
      'winRate',
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
    expect(KPI_HELP.realized).toContain('Realised today');
    expect(KPI_HELP.realizedToday).toContain('Always today');
  });
});

describe('dashboard tooltip copy (A4 audit)', () => {
  it('states the paper, gross, pre-tax basis on every performance figure', () => {
    for (const key of ['openPnl', 'winRate', 'expectancy', 'payoffRatio', 'realizedToday', 'realized'] as const) {
      expect(KPI_HELP[key], key).toContain(PERFORMANCE_CAVEAT);
    }
  });

  it('names ExpR and N beside the win rate', () => {
    expect(KPI_HELP.winRate).toContain('N is');
    expect(KPI_HELP.winRate).toContain('expectancy (ExpR)');
  });

  it('says Open P&L is an average percentage and a total in the account currency', () => {
    expect(KPI_HELP.openPnl).toContain('average percentage across those positions');
    expect(KPI_HELP.openPnl).toContain('account currency');
  });

  it('says Realised today runs on the Berlin day the server counts', () => {
    expect(KPI_HELP.realizedToday).toContain('Berlin day');
    expect(KPI_HELP.realizedToday).not.toContain('New York');
  });

  it('says Avg confidence reads the open positions, not the selected period', () => {
    expect(KPI_HELP.avgConfidence).toContain('positions open right now');
    expect(KPI_HELP.avgConfidence).not.toContain('in the selected period');
  });

  it('names how open risk is measured, not three horizons that do not exist', () => {
    expect(PANEL_HELP.exposureByHorizon).toContain('entry to the original stop');
    expect(PANEL_HELP.exposureByHorizon).not.toContain('short, medium, long');
  });
});
