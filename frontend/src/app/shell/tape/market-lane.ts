import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';

const SYMBOLS = [
  { proName: 'FOREXCOM:SPXUSD', title: 'S&P 500' },
  { proName: 'FOREXCOM:NSXUSD', title: 'Nasdaq 100' },
  { proName: 'FOREXCOM:DJI', title: 'Dow Jones' },
  { proName: 'CBOE:VIX', title: 'VIX' },
];

/**
 * Lane A — fixed market indices, from TradingView's ticker-tape widget.
 *
 * A third party in the shell, accepted deliberately: it is real-time, it costs
 * nothing to maintain, and it carries no swingbot data, which is exactly why
 * the iframe is tolerable here and would not be in Lane B. Its data cannot be
 * read out (cross-origin), which is the whole reason the tape has two lanes.
 *
 * **It must fail to absent, never to a broken box.** Note that an `error`
 * event does NOT fire reliably for a cross-origin iframe, so `failed` is a
 * best-effort escape hatch, not a guarantee. What actually carries the
 * requirement is CSS: the lane is a fixed 32px with `overflow: hidden`, so a
 * frame that never paints leaves an empty strip rather than a broken box, and
 * Lane B — a sibling, not a child — is unaffected either way.
 */
@Component({
  selector: 'sb-market-lane',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './tape.css',
  template: `
    @if (!failed()) {
      <div class="lane" role="region" aria-label="Market tape">
        <div class="cap">mkt</div>
        <div class="viewport">
          <iframe
            [src]="src()"
            title="Market index tape"
            height="32"
            width="100%"
            frameborder="0"
            scrolling="no"
            sandbox="allow-scripts allow-same-origin allow-popups"
            referrerpolicy="no-referrer"
            loading="lazy"
            (error)="failed.set(true)"
          ></iframe>
        </div>
        <div class="cap end">live</div>
      </div>
    }
  `,
})
export class MarketLane {
  private readonly sanitizer = inject(DomSanitizer);
  protected readonly failed = signal(false);
  protected readonly src = computed<SafeResourceUrl>(() => {
    const config = encodeURIComponent(JSON.stringify({
      symbols: SYMBOLS,
      colorTheme: 'dark',
      isTransparent: true,
      displayMode: 'adaptive',
      showSymbolLogo: true,
      width: '100%',
      height: 32,
    }));
    return this.sanitizer.bypassSecurityTrustResourceUrl(
      `https://s.tradingview.com/embed-widget/ticker-tape/#${config}`,
    );
  });
}
