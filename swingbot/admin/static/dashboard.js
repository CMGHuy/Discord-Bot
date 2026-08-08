/* ==========================================================================
 * Dashboard behaviour.
 *
 * Loaded ONCE by dashboard.html, from outside the auto-refreshing fragment.
 * That placement is the whole point of this file existing.
 *
 * All of this used to live in <script> tags inside dashboard_fragment.html --
 * markup that is re-fetched and morphdom-patched into the page every few
 * seconds. Scripts that arrive via DOM patching never execute (only scripts in
 * the originally-parsed HTML, or ones built with document.createElement, do),
 * which produced a family of bugs that all looked different and were all the
 * same bug:
 *
 *   - table blocks had to be rendered even when empty, because whether the
 *     paginator was DEFINED at all depended on whether the server happened to
 *     emit rows during that first page load;
 *   - every entry point had to be published on `window` so the poll loop could
 *     re-invoke it by hand after each patch;
 *   - the session banner needed a morphdom skip-rule to protect its own timer;
 *   - the shell's drag-and-drop handler called reorderTableColumns(), defined
 *     inside the very fragment it replaces.
 *
 * From out here none of that applies: this code is parsed once, its state
 * outlives every patch, and the fragment is pure markup. Handlers are
 * delegated from containers that are never themselves replaced, so nothing
 * needs re-binding; markup declares intent with data-* attributes
 * (data-confirm, data-no-row-click) rather than inline onclick/onsubmit.
 *
 * Server values arrive through the #dashboard-boot JSON block rather than
 * Jinja interpolation, since a static .js file is never templated.
 * ========================================================================== */
(function () {
  "use strict";

  var BOOT = JSON.parse(document.getElementById("dashboard-boot").textContent);

  var container = document.getElementById("dashboard-fragment");
  var mode = BOOT.mode;

  function $(id) { return document.getElementById(id); }
  function on(el, evt, fn) { if (el) el.addEventListener(evt, fn); }

  function readPref(key, fallback) {
    try { var v = localStorage.getItem(key); return v === null ? fallback : v; }
    catch (e) { return fallback; }
  }
  function writePref(key, value) {
    try { localStorage.setItem(key, value); } catch (e) {}
  }

  /* ---- Confirmations ----------------------------------------------------
   * One delegated handler for every `data-confirm` form on the page, in place
   * of a hand-written onsubmit="return confirm(...)" per form.
   */
  document.addEventListener("submit", function (e) {
    var msg = e.target.getAttribute && e.target.getAttribute("data-confirm");
    if (msg && !window.confirm(msg)) { e.preventDefault(); }
  });

  /* ---- Session banner ---------------------------------------------------
   * Tokyo/London/New York pills, from the browser's own UTC clock -- no
   * server data involved. Re-rendered after every fragment patch (the patch
   * restores the server's empty markup) and on its own each minute.
   */
  var SESSIONS = [
    { name: "Tokyo",    flag: "🗼", start: 0 * 60,        end: 9 * 60,        color: "#6ea8fe", bg: "rgba(110,168,254,0.12)" },
    { name: "London",   flag: "🏦", start: 8 * 60,        end: 16 * 60 + 30,  color: "#e2b25a", bg: "rgba(226,178,90,0.12)"  },
    { name: "New York", flag: "🗽", start: 13 * 60 + 30,  end: 20 * 60,       color: "#6dda9e", bg: "rgba(109,218,158,0.12)" }
  ];

  function pad(n) { return n < 10 ? "0" + n : String(n); }

  function renderSessionBanner() {
    var timeEl = $("session-time"), pillsEl = $("session-pills");
    if (!timeEl || !pillsEl) return;
    var now = new Date();
    var h = now.getUTCHours(), m = now.getUTCMinutes();
    var t = h * 60 + m;
    timeEl.textContent = pad(h) + ":" + pad(m) + " UTC";

    var active = SESSIONS.filter(function (s) { return t >= s.start && t < s.end; });
    if (!active.length) {
      pillsEl.innerHTML = '<span class="session-pill" style="color:#4a5470;border-color:#2a2e3d;background:#13161d;">⏸ Markets closed</span>';
      return;
    }
    var html = active.map(function (s) {
      return '<span class="session-pill" style="color:' + s.color + ';border-color:' + s.color +
             '55;background:' + s.bg + ';">' + s.flag + " " + s.name + "</span>";
    }).join("");
    if (active.length > 1) {
      html += '<span class="session-pill" style="color:#e2b25a;border-color:#e2b25a55;background:rgba(226,178,90,0.08);">⚡ Overlap — high liquidity</span>';
    }
    pillsEl.innerHTML = html;
  }

  setTimeout(function tick() {
    renderSessionBanner();
    setTimeout(tick, 60000);
  }, (60 - new Date().getUTCSeconds()) * 1000);

  /* ---- Shared table chrome ----------------------------------------------
   * Density toggle + page-size selector + Prev/Next, identical for both
   * tables. These were two near-copies differing only in element prefix and
   * storage key, which is exactly how the two tables drifted apart before.
   */
  function tableChrome(prefix, opts) {
    var densityKey = prefix + "_density";
    var perPageKey = prefix + "_per_page";
    var state = {
      density: readPref(densityKey, "compact"),
      perPage: parseInt(readPref(perPageKey, String(opts.defaultPerPage)), 10)
    };

    function applyDensity() {
      var wrap = document.querySelector('[data-density-for="' + prefix + '"]');
      if (wrap) {
        wrap.classList.toggle("density-compact", state.density === "compact");
        wrap.classList.toggle("density-full", state.density === "full");
      }
      document.querySelectorAll("#" + prefix + "-density-toggle button").forEach(function (b) {
        b.classList.toggle("active", b.dataset.density === state.density);
      });
    }

    // Density is presentation only -- it never refetches.
    document.querySelectorAll("#" + prefix + "-density-toggle button").forEach(function (b) {
      on(b, "click", function () {
        state.density = this.dataset.density;
        writePref(densityKey, state.density);
        applyDensity();
      });
    });

    var sel = $(prefix + "-per-page");
    if (sel) {
      sel.value = String(state.perPage);
      on(sel, "change", function () {
        state.perPage = parseInt(this.value, 10);
        writePref(perPageKey, state.perPage);
        opts.onPerPage();
      });
    }

    on($(prefix + "-prev"), "click", function () { opts.onPage(-1); });
    on($(prefix + "-next"), "click", function () { opts.onPage(1); });

    function setPager(page, pages, infoText) {
      var pageInfo = $(prefix + "-page-info"), info = $(prefix + "-info");
      var prev = $(prefix + "-prev"), next = $(prefix + "-next");
      if (pageInfo) pageInfo.textContent = "Page " + page + " / " + pages;
      if (info) info.textContent = infoText;
      if (prev) prev.disabled = page <= 1;
      if (next) next.disabled = page >= pages;
    }

    state.applyDensity = applyDensity;
    state.setPager = setPager;
    applyDensity();
    return state;
  }

  /* ---- Open Trades table ------------------------------------------------
   * Filtered, sorted and paginated in the browser: the whole set is already
   * in the DOM (open positions are few), so there is nothing to fetch.
   * Trade History does the opposite for the opposite reason -- see below.
   */
  var otPage = 1;
  var otSortCol = null, otSortAsc = false;
  var otRows = [];

  var ot = tableChrome("ot", {
    defaultPerPage: 25,
    onPerPage: function () { otPage = 1; otRender(); },
    onPage: function (delta) { otPage += delta; otRender(); }
  });

  function otTable() { return $("trades-table"); }

  // A scaled-out trade's .ot-leg-row is a continuation of its parent, never a
  // row to paginate or sort on its own.
  function otLegRows(row) {
    var id = row.dataset.tradeId;
    if (!id) return [];
    return Array.from(document.querySelectorAll(
      '#trades-table tbody tr.ot-leg-row[data-leg-for="' + id + '"]'));
  }

  function otScan() {
    otRows = Array.from(document.querySelectorAll("#trades-table tbody tr:not(.ot-leg-row)"));
  }

  function otColIndex(colId) {
    var ths = document.querySelectorAll("#trades-table thead th[data-col-id]");
    for (var i = 0; i < ths.length; i++) {
      if (ths[i].dataset.colId === colId) return i;
    }
    return -1;
  }

  function otSort(colId) {
    if (otSortCol === colId) { otSortAsc = !otSortAsc; } else { otSortCol = colId; otSortAsc = false; }
    otApplySort();
    otPage = 1;
    otRender();
  }

  function otApplySort() {
    if (!otSortCol) return;
    var idx = otColIndex(otSortCol);
    var tbody = document.querySelector("#trades-table tbody");
    if (idx === -1 || !tbody) return;
    var rows = Array.from(tbody.querySelectorAll("tr:not(.ot-leg-row)"));
    rows.sort(function (a, b) {
      var ac = a.cells[idx], bc = b.cells[idx];
      if (!ac || !bc) return 0;
      var av = (ac.dataset.sort !== undefined ? ac.dataset.sort : ac.innerText).trim();
      var bv = (bc.dataset.sort !== undefined ? bc.dataset.sort : bc.innerText).trim();
      var an = parseFloat(av), bn = parseFloat(bv);
      var cmp = (!isNaN(an) && !isNaN(bn)) ? (an - bn) : av.localeCompare(bv);
      return otSortAsc ? cmp : -cmp;
    });
    rows.forEach(function (r) {
      tbody.appendChild(r);
      otLegRows(r).forEach(function (leg) { tbody.appendChild(leg); });
    });
    document.querySelectorAll("#trades-table .sort-arrow").forEach(function (el) {
      el.textContent = (el.dataset.colId === otSortCol) ? (otSortAsc ? " ▲" : " ▼") : "";
    });
    otScan();
  }

  function otRender() {
    var q = (($("trade-filter") || {}).value || "").toLowerCase();
    var visible = otRows.filter(function (row) {
      return !q || row.innerText.toLowerCase().includes(q);
    });
    var total = visible.length;
    var pp = ot.perPage === 0 ? total : ot.perPage;
    var pages = pp > 0 ? Math.max(1, Math.ceil(total / pp)) : 1;
    otPage = Math.max(1, Math.min(otPage, pages));
    var start = (otPage - 1) * pp;
    var end = Math.min(start + pp, total);

    document.querySelectorAll("#trades-table tbody tr").forEach(function (r) {
      r.style.display = "none";
    });
    visible.slice(start, end).forEach(function (r) {
      r.style.display = "";
      otLegRows(r).forEach(function (leg) { leg.style.display = ""; });
    });

    ot.setPager(otPage, pages,
      total === 0 ? "No matching trades" : "Showing " + (start + 1) + "–" + end + " of " + total);
  }

  function otRefresh() {
    otScan();
    ot.applyDensity();
    otApplySort();
    otRender();
  }

  /* ---- Trade History table ----------------------------------------------
   * Served a page at a time by /api/trade-history. Scoping, all six filters,
   * sorting and slicing are server-side, and they have to be: with paged
   * responses, DOM-hiding filters would silently mean "AAPL among these 25".
   *
   * The rows come back as rendered HTML from the same partial the first paint
   * uses, so a fetched page is indistinguishable from the initial one and
   * there is no second copy of the row markup in JS.
   */
  var ctPage = 1;
  var ctSortCol = null, ctSortAsc = false;
  var ctFilters = {};
  var ctSeq = 0;              // guards against out-of-order responses
  var ctDebounce = null;

  var ct = tableChrome("ct", {
    defaultPerPage: 10,
    onPerPage: function () { ctReload(true); },
    onPage: function (delta) {
      if (delta < 0 && ctPage <= 1) return;
      ctPage += delta;
      ctLoad();
    }
  });

  function ctQuery() {
    var q = new URLSearchParams();
    q.set("mode", mode);
    q.set("page", String(ctPage));
    q.set("per_page", String(ct.perPage));
    Object.keys(ctFilters).forEach(function (k) {
      if (ctFilters[k]) q.set(k, ctFilters[k]);
    });
    if (ctSortCol) {
      q.set("sort_by", ctSortCol);
      q.set("sort_dir", ctSortAsc ? "asc" : "desc");
    }
    return q.toString();
  }

  function ctLoad() {
    var seq = ++ctSeq;
    var tbody = document.querySelector("#closed-trades-table tbody");
    if (!tbody) return;
    fetch(BOOT.historyUrl + "?" + ctQuery(), { credentials: "same-origin" })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (d) {
        if (seq !== ctSeq) return;             // a newer request already won
        tbody.innerHTML = d.rows_html;
        var start = d.total === 0 ? 0 : (d.page - 1) * (ct.perPage || d.total) + 1;
        var end = d.total === 0 ? 0 : start + d.shown - 1;
        ct.setPager(d.page, d.pages,
          d.total === 0 ? "No matching trades" : "Showing " + start + "–" + end + " of " + d.total);
        var count = $("ct-total-count");
        if (count) count.textContent = d.total;
        document.querySelectorAll("#closed-trades-table .sort-arrow").forEach(function (el) {
          el.textContent = (el.dataset.colId === ctSortCol) ? (ctSortAsc ? " ▲" : " ▼") : "";
        });
        ct.applyDensity();
      })
      .catch(function (err) {
        if (seq !== ctSeq) return;
        // Leave the rows already on screen -- a transient fetch failure should
        // not blank the table out from under the user.
        var info = $("ct-info");
        if (info) info.textContent = "Could not load trade history (" + err.message + ")";
      });
  }

  // Debounced so spinning through a dropdown does not stack one request per
  // keystroke; the seq guard above handles any that do overlap.
  function ctReload(resetPage) {
    if (resetPage) ctPage = 1;
    clearTimeout(ctDebounce);
    ctDebounce = setTimeout(ctLoad, 150);
  }

  document.querySelectorAll(".ct-filter").forEach(function (el) {
    on(el, "change", function () {
      ctFilters[el.dataset.filter] = el.value;
      ctReload(true);
    });
  });

  on($("ct-reset-filters"), "click", function () {
    document.querySelectorAll(".ct-filter").forEach(function (el) { el.value = ""; });
    ctFilters = {};
    ctReload(true);
  });

  /* ---- Column order (Open Trades) ---------------------------------------
   * Delegated on #dashboard-fragment, which is never itself replaced -- only
   * its contents are. A handler bound to a <th> would be destroyed the moment
   * that element is patched.
   */
  var COLUMN_ORDER_KEY = "swingbot_dashboard_column_order";
  var dragSrcColId = null;

  function reorderColumns(table, targetOrder) {
    var headRow = table.querySelector("thead tr");
    var currentIds = Array.from(headRow.children).map(function (th) { return th.dataset.colId; });
    var indices = targetOrder
      .map(function (id) { return currentIds.indexOf(id); })
      .filter(function (i) { return i !== -1; });
    if (indices.length !== currentIds.length) return;
    table.querySelectorAll("tr").forEach(function (row) {
      var cells = Array.from(row.children);
      if (cells.length !== currentIds.length) return;
      indices.forEach(function (i) { row.appendChild(cells[i]); });
    });
  }

  function applyColumnOrder() {
    var table = otTable();
    if (!table) return;
    var saved;
    try { saved = JSON.parse(readPref(COLUMN_ORDER_KEY, "null")); } catch (e) { saved = null; }
    if (!saved) return;
    var headRow = table.querySelector("thead tr");
    var currentIds = Array.from(headRow.children).map(function (th) { return th.dataset.colId; });
    var target = saved.filter(function (id) { return currentIds.indexOf(id) !== -1; });
    currentIds.forEach(function (id) { if (target.indexOf(id) === -1) target.push(id); });
    reorderColumns(table, target);
  }

  on(container, "dragstart", function (e) {
    var th = e.target.closest("th[data-col-id]");
    if (!th) return;
    dragSrcColId = th.dataset.colId;
    e.dataTransfer.effectAllowed = "move";
    th.classList.add("dragging-col");
  });

  on(container, "dragover", function (e) {
    if (!dragSrcColId) return;
    var th = e.target.closest("th[data-col-id]");
    if (!th) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    th.classList.add("drop-target-col");
  });

  on(container, "dragleave", function (e) {
    var th = e.target.closest("th[data-col-id]");
    if (th) th.classList.remove("drop-target-col");
  });

  on(container, "drop", function (e) {
    var th = e.target.closest("th[data-col-id]");
    if (th) th.classList.remove("drop-target-col");
    if (!th || !dragSrcColId) return;
    e.preventDefault();
    var table = otTable();
    if (!table || th.dataset.colId === dragSrcColId) return;
    var headRow = table.querySelector("thead tr");
    var order = Array.from(headRow.children).map(function (el) { return el.dataset.colId; });
    var fromIdx = order.indexOf(dragSrcColId);
    var toIdx = order.indexOf(th.dataset.colId);
    if (fromIdx === -1 || toIdx === -1) return;
    order.splice(fromIdx, 1);
    order.splice(toIdx, 0, dragSrcColId);
    reorderColumns(table, order);
    writePref(COLUMN_ORDER_KEY, JSON.stringify(order));
  });

  on(container, "dragend", function (e) {
    var th = e.target.closest("th[data-col-id]");
    if (th) th.classList.remove("dragging-col");
    container.querySelectorAll(".drop-target-col").forEach(function (el) {
      el.classList.remove("drop-target-col");
    });
    dragSrcColId = null;
  });

  /* ---- Delegated table interactions -------------------------------------
   * Sort headers and the Open Trades filter box live inside the polled
   * fragment, so their listeners are delegated from containers that outlive
   * every patch rather than bound to the elements themselves.
   */
  on(container, "click", function (e) {
    var th = e.target.closest("#trades-table thead th[data-col-id]");
    if (th && th.dataset.sortable !== "false") { otSort(th.dataset.colId); }
  });

  on(container, "input", function (e) {
    if (e.target.id === "trade-filter") { otPage = 1; otRender(); }
  });

  on(document, "click", function (e) {
    var th = e.target.closest("#closed-trades-table thead th[data-col-id]");
    if (!th) return;
    var colId = th.dataset.colId;
    if (ctSortCol === colId) { ctSortAsc = !ctSortAsc; } else { ctSortCol = colId; ctSortAsc = false; }
    ctReload(true);
  });

  /* ---- Dashboard mode ---------------------------------------------------
   * Reflected in the URL (?mode=...) so the choice is visible, shareable and
   * survives a reload of THAT url. Deliberately NOT persisted in
   * localStorage: it used to be, which silently reapplied a forgotten
   * "Today only" to every future page load -- and "Today only" hides open
   * positions not opened today by design, so one old click could make a live
   * trade vanish from every load afterwards, explained only by a
   * re-highlighted toggle button that is easy to miss.
   */
  function paintModeButtons() {
    document.querySelectorAll(".dashboard-mode-btn").forEach(function (btn) {
      var active = btn.dataset.mode === mode;
      btn.classList.toggle("active", active);
      btn.setAttribute("aria-pressed", active ? "true" : "false");
    });
  }

  on($("dashboard-mode-toggle"), "click", function (e) {
    var btn = e.target.closest(".dashboard-mode-btn");
    if (!btn || btn.dataset.mode === mode) return;
    mode = btn.dataset.mode;
    var url = new URL(window.location.href);
    url.searchParams.set("mode", mode);
    window.history.replaceState(null, "", url);
    paintModeButtons();
    refreshDashboard();
  });

  /* ---- Fragment auto-refresh --------------------------------------------- */
  var lastEtag = null;

  function refreshDashboard() {
    var headers = {};
    if (lastEtag) headers["If-None-Match"] = lastEtag;
    fetch(BOOT.fragmentUrl + "?mode=" + encodeURIComponent(mode),
          { credentials: "include", headers: headers })
      .then(function (r) {
        if (r.status === 401) { window.location.reload(); return null; }
        if (r.status === 304) return undefined;   // unchanged -- nothing to patch
        lastEtag = r.headers.get("ETag");
        return r.text();
      })
      .then(function (html) {
        var status = $("refresh-status");
        if (html === undefined) {
          if (status) status.textContent = "Up to date " + new Date().toLocaleTimeString();
          return;
        }
        if (!html || !container) return;

        if (typeof morphdom !== "undefined") {
          // Diff-patch rather than innerHTML: only nodes that actually changed
          // are touched, which avoids the full repaint/layout-thrash that made
          // every refresh visibly flash.
          var wrapper = document.createElement("div");
          wrapper.id = "dashboard-fragment";
          wrapper.innerHTML = html;
          morphdom(container, wrapper, {
            onBeforeElUpdated: function (from) {
              // Keep what the user is currently typing in / has focused.
              return !(from.nodeName === "INPUT" || from.nodeName === "SELECT");
            }
          });
        } else {
          container.innerHTML = html;
        }

        // The patch restored the server's markup, so anything this file owns
        // has to be reapplied. Unlike before, these are ordinary local calls,
        // not globals published for the poll loop to find.
        applyColumnOrder();
        otRefresh();
        renderSessionBanner();
        if (status) status.textContent = "Updated " + new Date().toLocaleTimeString();

        // Brief "this just refreshed" flash on the stat cards. Re-triggering a
        // CSS animation on an element that already has the class requires
        // forcing a reflow between remove and re-add, or the browser treats
        // the second add as a no-op.
        document.querySelectorAll(".stat-card").forEach(function (el) {
          el.classList.remove("just-updated");
          void el.offsetWidth;
          el.classList.add("just-updated");
        });
      })
      .catch(function () {});
  }

  on($("refresh-now"), "click", refreshDashboard);
  setInterval(function () {
    var box = $("auto-refresh");
    if (box && box.checked) refreshDashboard();
  }, BOOT.refreshSeconds * 1000);

  /* ---- Scan status + bot liveness ---------------------------------------- */
  function refreshScanStatus() {
    fetch(BOOT.scanStatusUrl, { credentials: "include" })
      .then(function (r) { return r.status === 401 ? null : r.json(); })
      .then(function (data) {
        if (!data) return;

        var btn = $("pause-resume-btn"), form = $("pause-resume-form"), badge = $("scan-pause-badge");
        if (btn && form && badge) {
          if (data.paused) {
            btn.textContent = "▶ Resume scanning";
            btn.title = "Resume the automatic background scan loop";
            form.action = BOOT.resumeUrl;
            form.setAttribute("data-confirm", "Resume automatic scanning?");
            badge.style.display = "inline-block";
            badge.textContent = "⏸ Paused";
            badge.style.color = "#e2b25a";
            badge.style.borderColor = "#e2b25a";
          } else {
            btn.textContent = "⏸ Pause scanning";
            btn.title = "Pause the automatic background scan loop (manual !check still works)";
            form.action = BOOT.pauseUrl;
            form.setAttribute("data-confirm",
              'Pause automatic scanning? Manual !check and "Run !check now" will still work.');
            badge.style.display = "none";
          }
        }

        // "Stop scan" only makes sense while a scan is actually in progress.
        var stopBtn = $("stop-btn");
        if (stopBtn) stopBtn.disabled = !data.running;

        var dot = $("bot-status-dot"), label = $("bot-status-label"), wrap = $("bot-status-wrap");
        if (!dot || !label) return;

        if (data.bot_alive) {
          var text = "Bot: 🟢 active";
          if (data.bot_session_active === false) text = "Bot: 🟡 online (off-hours)";
          if (data.bot_scan_paused) text = "Bot: ⏸ paused";
          var lastSeen = data.bot_last_seen
            ? " · last seen " + new Date(data.bot_last_seen).toLocaleTimeString()
            : "";
          dot.style.setProperty("--status-color", data.bot_scan_paused ? "#e2b25a"
                                : data.bot_session_active ? "#26a69a" : "#6ea8fe");
          dot.style.setProperty("--blink-duration", "2.2s");
          label.textContent = text + lastSeen;
          if (wrap) wrap.title = "Bot process is alive" + lastSeen;
        } else if (data.bot_last_seen) {
          // Heartbeat file exists but is stale -- the bot has gone quiet.
          var ago = Math.round((Date.now() - new Date(data.bot_last_seen).getTime()) / 1000);
          var agoStr = ago < 120 ? ago + "s ago" : Math.round(ago / 60) + "m ago";
          dot.style.setProperty("--status-color", "#ef5350");
          dot.style.setProperty("--blink-duration", "0.8s");
          label.textContent = "Bot: 🔴 offline (last seen " + agoStr + ")";
          if (wrap) wrap.title = "Bot process has not responded in over " + agoStr;
        } else {
          // No heartbeat file at all (first run, or deleted) -- neutral grey
          // rather than an alarming red.
          dot.style.setProperty("--status-color", "#5a6275");
          dot.style.setProperty("--blink-duration", "2.2s");
          label.textContent = "Bot: status unknown";
          if (wrap) wrap.title = "No heartbeat file found — bot may not be running yet";
        }
      })
      .catch(function () {});
  }

  /* ---- Chart preview modal ----------------------------------------------- */
  var modal = $("chart-modal");
  var chartHost = $("chart-modal-chart");

  function closeModal() {
    if (!modal) return;
    modal.hidden = true;
    chartHost.innerHTML = "";
  }

  on(document, "click", function (e) {
    if (!modal) return;
    var row = e.target.closest("tr[data-ticker]");
    if (row && !e.target.closest("a, button, form, [data-no-row-click]")) {
      modal.hidden = false;
      $("chart-modal-title").textContent = row.dataset.ticker;
      chartHost.innerHTML = "";
      chartHost.dataset.ticker = row.dataset.ticker;
      SwingChart.mount(chartHost);
    }
    if (e.target === modal || e.target.id === "chart-modal-close") closeModal();
  });

  on(document, "keydown", function (e) { if (e.key === "Escape") closeModal(); });

  /* ---- Boot -------------------------------------------------------------- */
  paintModeButtons();
  renderSessionBanner();
  applyColumnOrder();
  otRefresh();
  ctLoad();
  refreshScanStatus();
  setInterval(refreshScanStatus, 5000);
})();
