import {
  ChangeDetectionStrategy,
  Component,
  TemplateRef,
  computed,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { Router, RouterLink } from '@angular/router';

import { Ticker } from '../../api/models';
import { WatchlistStore } from '../../stores/watchlist.store';
import { Button } from '../../ui/button';
import { ConfirmDialog } from '../../ui/confirm-dialog';
import { DataTable } from '../../ui/data-table/data-table';
import { ColumnDef, RowContext } from '../../ui/data-table/data-table.types';
import { text } from '../../ui/format';
import { Panel } from '../../ui/layout';

/**
 * Watchlist — the watchlist the scanner walks.
 *
 * Deliberately the thinnest workspace (spec v14 Decision 9): a table, an add
 * box and a remove button. Everything interesting about a symbol is one
 * click away on its detail view, and nothing here duplicates it.
 *
 * **One add box for single and bulk.** The endpoint absorbs both, so a
 * separate "bulk import" would be a second path to the same place with its
 * own validation to drift. Type one symbol and press Enter, or paste thirty
 * — the box splits on commas and whitespace either way, and the result names
 * what was added, what was already there and what was rejected.
 *
 * `DataTableComponent` is the fourth and last of its call sites (spec v14's
 * definition of done, property 3). A second table implementation anywhere is
 * a defect, and this screen is small enough to have been tempting.
 */
@Component({
  selector: 'sb-watchlist',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, DataTable, Panel, Button, ConfirmDialog],
  providers: [WatchlistStore],
  template: `
    <header class="head">
      <h1>Watchlist</h1>
      <span class="count">{{ store.count() }} watched</span>
      @if (store.error(); as message) {
        <span class="stale" role="status">{{ message }}</span>
      }
    </header>

    <sb-panel heading="Add tickers">
      <div class="add">
        <div class="box">
          <input
            class="input"
            type="text"
            [value]="entry()"
            (input)="onEntry($any($event.target).value)"
            (keydown.enter)="add()"
            (blur)="closeSuggestions()"
            placeholder="AAPL, or paste a list"
            aria-label="Ticker symbols to add"
          />

          @if (store.suggestions().length) {
            <!-- mousedown, not click: blur fires first on a click and would
                 close the list before the handler ran. -->
            <ul class="suggestions">
              @for (hit of store.suggestions(); track hit.symbol) {
                <li>
                  <button type="button" (mousedown)="pick(hit.symbol)">
                    <span class="hit-symbol">{{ hit.symbol }}</span>
                    <span class="hit-name">{{ hit.name }}</span>
                    @if (store.symbols().has(hit.symbol)) {
                      <!-- Said before the round trip, because being told
                           "already watched" by the server is a request the
                           screen already had the answer to. -->
                      <span class="hit-have">watched</span>
                    }
                  </button>
                </li>
              }
            </ul>
          }
        </div>

        <button
          sb-button
          variant="primary"
          type="button"
          [loading]="store.adding()"
          [disabled]="!entry().trim()"
          (click)="add()"
        >
          Add
        </button>
      </div>

      @if (store.addResult(); as message) {
        <p class="result" role="status">{{ message }}</p>
      }
      @if (store.addError(); as message) {
        <p class="error" role="alert">{{ message }}</p>
      }
    </sb-panel>

    @if (store.removeError(); as message) {
      <p class="error" role="alert">{{ message }}</p>
    }

    <sb-panel heading="Watchlist" [flush]="true">
      <sb-data-table
        [rows]="store.tickers()"
        [columns]="columns()"
        [visible]="visible"
        [rowKey]="rowKey"
        [loading]="store.loading() && store.empty()"
        [emptyState]="emptyState"
        (rowActivate)="open($event)"
      />
    </sb-panel>

    <sb-confirm-dialog
      [open]="pending() !== null"
      title="Remove from the watchlist"
      [consequence]="consequence()"
      confirmLabel="Remove"
      [working]="store.removing() !== null"
      (confirmed)="remove()"
      (cancelled)="pending.set(null)"
    />

    <!-- cells ----------------------------------------------------------- -->

    <ng-template #symbolCell let-row>
      <a class="row-link" [routerLink]="['/watchlist', row.symbol]">{{ row.symbol }}</a>
    </ng-template>

    <ng-template #actionsCell let-row>
      <button sb-button variant="ghost" type="button" (click)="ask(row)">Remove</button>
    </ng-template>
  `,
  styles: `
    :host { display: grid; gap: var(--space-20); }

    .head { display: flex; align-items: baseline; gap: var(--space-14); }
    h1 { margin: 0; font-size: var(--text-title); font-weight: 600; }
    .count { color: var(--text-secondary); font-size: var(--text-table); }
    .stale { color: var(--warn); font-size: var(--text-table); }

    .add { display: flex; align-items: flex-start; gap: var(--space-8); }
    .box { position: relative; flex: 1 1 auto; max-width: 420px; }
    .input {
      width: 100%;
      padding: var(--space-6) var(--space-8);
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      color: var(--text);
      font-family: var(--font-mono);
      font-size: var(--text-table);
    }
    .input:focus-visible { outline: 1px solid var(--accent); outline-offset: 1px; }
    .input::placeholder { color: var(--text-faint); font-family: var(--font-sans); }

    .suggestions {
      position: absolute;
      z-index: 2;
      inset-inline: 0;
      margin-top: var(--space-4);
      max-height: 240px;
      overflow-y: auto;
      background: var(--surface-raised);
      border: 1px solid var(--border-strong);
      border-radius: var(--radius);
    }
    .suggestions button {
      display: flex;
      align-items: baseline;
      gap: var(--space-8);
      width: 100%;
      padding: var(--space-4) var(--space-8);
      background: transparent;
      border: 0;
      color: var(--text);
      font: inherit;
      font-size: var(--text-table);
      text-align: left;
      cursor: pointer;
    }
    .suggestions button:hover { background: var(--surface); }
    .hit-symbol { font-family: var(--font-mono); }
    .hit-name { color: var(--text-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .hit-have { margin-left: auto; color: var(--text-faint); font-size: var(--text-chip); }

    .result { margin-top: var(--space-10); color: var(--text-secondary); font-size: var(--text-table); }
    .error { color: var(--neg); font-size: var(--text-table); }

    .row-link { color: var(--accent); font-family: var(--font-mono); text-decoration: none; }
    .row-link:hover { text-decoration: underline; }
  `,
})
export class Watchlist {
  private readonly router = inject(Router);
  protected readonly store = inject(WatchlistStore);

  protected readonly entry = signal('');
  /** The row awaiting confirmation, or null. */
  protected readonly pending = signal<Ticker | null>(null);

  protected readonly rowKey = (row: Ticker) => row.symbol;

  protected readonly emptyState = {
    title: 'Nothing on the watchlist',
    hint: 'Add a symbol above and the scanner will start covering it.',
  };

  private readonly symbolCell =
    viewChild.required<TemplateRef<RowContext<Ticker>>>('symbolCell');
  private readonly actionsCell =
    viewChild.required<TemplateRef<RowContext<Ticker>>>('actionsCell');

  protected readonly visible = ['symbol', 'company_name', 'open_trades', 'closed_trades', 'actions'];

  protected readonly columns = computed<ColumnDef<Ticker>[]>(() => [
    { key: 'symbol', header: 'Symbol', cell: this.symbolCell() },
    { key: 'company_name', header: 'Company', value: (row) => text(row.company_name) },
    { key: 'open_trades', header: 'Open', value: (row) => row.open_trades, numeric: true },
    { key: 'closed_trades', header: 'Closed', value: (row) => row.closed_trades, numeric: true },
    { key: 'actions', header: '', cell: this.actionsCell(), width: '1%' },
  ]);

  protected readonly consequence = computed(() => {
    const row = this.pending();
    if (!row) return '';
    const held = row.open_trades
      ? ` It has ${row.open_trades} open position${row.open_trades === 1 ? '' : 's'}, which stay open and keep being monitored.`
      : '';
    // Naming what does NOT happen matters as much here: removing a symbol
    // stops future scanning, and someone expecting it to close positions
    // would be wrong in the dangerous direction.
    return `${row.symbol} will no longer be scanned for new setups.${held} Its trade history is kept.`;
  });

  protected onEntry(value: string): void {
    this.entry.set(value);
    // Only the last fragment is a query: pasting a list should not fire a
    // suggestion request for the whole blob.
    const last = value.split(/[,\s]+/).pop() ?? '';
    this.store.suggest(last);
  }

  protected pick(symbol: string): void {
    // Replaces the fragment being typed, keeping anything already entered
    // before it — so picking from the list works mid-paste as well.
    const parts = this.entry().split(/[,\s]+/);
    parts[parts.length - 1] = symbol;
    this.entry.set(parts.join(', '));
    this.store.clearSuggestions();
  }

  protected closeSuggestions(): void {
    this.store.clearSuggestions();
  }

  protected add(): void {
    this.store.addTickers(this.entry());
    this.entry.set('');
  }

  protected ask(row: Ticker): void {
    this.pending.set(row);
  }

  protected remove(): void {
    const row = this.pending();
    if (!row) return;
    this.store.removeTicker(row.symbol);
    this.pending.set(null);
  }

  protected open(row: Ticker): void {
    void this.router.navigate(['/watchlist', row.symbol]);
  }
}
