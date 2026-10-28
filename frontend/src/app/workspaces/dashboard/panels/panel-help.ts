/**
 * What each Dashboard panel and KPI card is about -- the tooltip copy.
 *
 * One file so the wording is read and reviewed in one place, and a spec can
 * assert that no panel or card on the page goes without. Plain words first:
 * the partner reads these while hovering to find out what a figure means, so
 * each says what is counted, over which period, and how to read the number.
 */
import { PERFORMANCE_CAVEAT } from '../../../ui/stat-tile';

export const PANEL_HELP = {
  tradingPerformance:
    'Your paper account at a glance: its value, the change today and the equity chart, then the '
    + 'figures for the period selected above (1D, 5D … All, or the range you dragged the chart to). '
    + 'Simulated trades, before tax and costs.',
  openPositions:
    'Every trade plan by stage: pending (waiting for entry), active (entered), partial (first target '
    + 'banked, the rest still running) and closed. Open one to see why it was taken.',
  recentActivity:
    'The latest events on your trade plans, newest first: entries, partial exits, exits and cancellations.',
  marketMovers:
    'The biggest price moves today among the symbols on your watchlist, winners and losers.',
  exposureByHorizon:
    'How much of your open risk sits in each swing horizon, as a share of the total. Risk is the shares '
    + 'still open times the distance from entry to the original stop.',
  watchlist:
    'The symbols being scanned, with their latest price and the change over the day.',
} as const;

export const KPI_HELP = {
  openPnl:
    'Profit or loss right now on the positions that are still open: the average percentage across those '
    + 'positions, and the total in the account currency. Not locked in until they close. '
    + PERFORMANCE_CAVEAT,
  winRate:
    'The share of closed trades that finished in profit in the selected period. Each realised leg of a '
    + 'plan that scaled out counts as its own trade; N is how many closed trades it counts. A high win rate alone is not enough: read it with the expectancy (ExpR) and the '
    + 'payoff ratio. ' + PERFORMANCE_CAVEAT,
  expectancy:
    'The average result per closed trade, in R (one R is the amount risked on that trade); each '
    + 'realised leg of a plan that scaled out counts as its own trade. Above 0 '
    + 'the approach earns on average; below 0 it loses. ' + PERFORMANCE_CAVEAT,
  payoffRatio:
    'The average winning trade divided by the average losing trade, both in R. 2.0 means a typical '
    + 'win is twice the size of a typical loss. Together with the win rate it explains the expectancy: '
    + 'a low win rate can still pay if the payoff ratio is high. ' + PERFORMANCE_CAVEAT,
  realizedToday:
    'Profit or loss locked in by trades that closed today (Berlin day), with how many closed and '
    + 'how many won or lost. Always today, whatever period is selected. ' + PERFORMANCE_CAVEAT,
  realized:
    'Profit or loss from trades closed in the selected period, in the account currency. Shown only when a '
    + 'period other than Today is selected; Realised today sits beside it. ' + PERFORMANCE_CAVEAT,
  openTrades: 'How many positions are open right now.',
  avgConfidence:
    'The average confidence score of the alerts behind the positions open right now, whatever period '
    + 'is selected.',
} as const;
