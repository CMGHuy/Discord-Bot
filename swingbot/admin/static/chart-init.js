/* Interactive chart bootstrap — themed from tokens.css at runtime so the
   chart always matches the page. Requires vendored lightweight-charts 4.x. */
(function () {
  "use strict";
  function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }
  function levelLine(series, price, color, title) {
    if (price == null) return;
    series.createPriceLine({ price: price, color: color, lineWidth: 1,
      lineStyle: LightweightCharts.LineStyle.Dashed, axisLabelVisible: true, title: title });
  }
  async function mount(el) {
    const ticker = el.dataset.ticker;
    if (!ticker) return;
    const qs = new URLSearchParams({ bars: el.dataset.bars || "260" });
    if (el.dataset.tradeId) qs.set("trade_id", el.dataset.tradeId);
    const resp = await fetch(`/api/ohlcv/${encodeURIComponent(ticker)}?` + qs);
    if (!resp.ok) { el.innerHTML = '<div class="empty-state">No chart data.</div>'; return; }
    const data = await resp.json();

    const chart = LightweightCharts.createChart(el, {
      autoSize: true,
      layout: { background: { color: cssVar("--bg-1") }, textColor: cssVar("--text-3"),
                fontFamily: cssVar("--font-sans") },
      grid: { vertLines: { color: cssVar("--border-1") }, horzLines: { color: cssVar("--border-1") } },
      crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
      rightPriceScale: { borderColor: cssVar("--border-2") },
      timeScale: { borderColor: cssVar("--border-2") },
    });
    const candles = chart.addCandlestickSeries({
      upColor: cssVar("--up"), downColor: cssVar("--down"),
      wickUpColor: cssVar("--up"), wickDownColor: cssVar("--down"), borderVisible: false,
    });
    candles.setData(data.bars);
    const vol = chart.addHistogramSeries({ priceFormat: { type: "volume" },
      priceScaleId: "vol" });
    chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    vol.setData(data.bars.map(b => ({ time: b.time, value: b.volume,
      color: b.close >= b.open ? cssVar("--up") + "55" : cssVar("--down") + "55" })));

    if (data.levels) {
      levelLine(candles, data.levels.entry, cssVar("--accent"), "Entry");
      levelLine(candles, data.levels.stop_loss, cssVar("--down"), "SL");
      levelLine(candles, data.levels.tp1, cssVar("--up"), "TP1");
      levelLine(candles, data.levels.tp2, cssVar("--purple"), "TP2");
    }

    // Crosshair OHLC legend (top-left, TradingView style)
    const legend = document.createElement("div");
    legend.className = "chart-legend";
    el.style.position = "relative";
    el.appendChild(legend);
    const last = data.bars[data.bars.length - 1];
    function renderLegend(b) {
      const dir = b.close >= b.open ? "pos" : "neg";
      legend.textContent = "";

      const tickerB = document.createElement("b");
      tickerB.textContent = data.ticker;
      legend.appendChild(tickerB);

      legend.appendChild(document.createTextNode(" · O "));

      const oSpan = document.createElement("span");
      oSpan.className = dir;
      oSpan.textContent = b.open;
      legend.appendChild(oSpan);

      legend.appendChild(document.createTextNode(" H "));

      const hSpan = document.createElement("span");
      hSpan.className = dir;
      hSpan.textContent = b.high;
      legend.appendChild(hSpan);

      legend.appendChild(document.createTextNode(" L "));

      const lSpan = document.createElement("span");
      lSpan.className = dir;
      lSpan.textContent = b.low;
      legend.appendChild(lSpan);

      legend.appendChild(document.createTextNode(" C "));

      const cSpan = document.createElement("span");
      cSpan.className = dir;
      cSpan.textContent = b.close;
      legend.appendChild(cSpan);
    }
    renderLegend(last);
    chart.subscribeCrosshairMove(p => {
      const b = p && p.seriesData ? p.seriesData.get(candles) : null;
      renderLegend(b && b.open !== undefined ? b : last);
    });
    chart.timeScale().fitContent();
    return chart;
  }
  window.SwingChart = { mount };
  document.addEventListener("DOMContentLoaded", () =>
    document.querySelectorAll("[data-swing-chart]").forEach(mount));
})();
