def test_trade_detail_shows_static_image_before_interactive_chart(client, auth):
    from swingbot.admin.app import _trades
    tl = _trades()
    trade_id = tl.log_trade(ticker="AAPL", strategy="RSI", horizon_key="4w",
                             direction="bullish", confidence_level=4,
                             confidence_label="Strong", entry=100.0,
                             stop_loss=95.0, take_profit=110.0)

    r = client.get(f"/trades/{trade_id}", headers=auth)
    assert r.status_code == 200
    html = r.data.decode("utf-8")

    img_pos = html.index('id="chart-img"')
    chart_pos = html.index('data-swing-chart')
    assert img_pos < chart_pos, "generated plan image must appear before the interactive chart"

    # Visualization and Trade facts must no longer share a grid row --
    # Trade facts is now a separate full-width card below.
    assert 'class="detail-grid"' not in html
