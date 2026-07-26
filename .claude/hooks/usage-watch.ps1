# Warns when any Claude profile's usage limit crosses a threshold (default 90%).
#
# There is NO usage/quota hook event in Claude Code, so this cannot be event-driven
# off the limit itself. Instead it reads the live quota cache that each profile
# maintains at <CLAUDE_CONFIG_DIR>/.claude.json:
#
#   cachedUsageUtilization.utilization.limits[] =
#       { kind: "session" | "weekly_all", percent: 23, severity, resets_at, is_active }
#
# and is invoked from cheap, frequent hooks (SessionStart + Stop). That makes it a
# poll, not a push: `percent` is only as fresh as the last time some session fetched
# it (fetchedAtMs). Whichever profile is actively working keeps its own cache warm,
# which is exactly the profile whose limit matters.
#
# Covers ALL profiles under the config root, not just the one running this session -
# the point is to see the ceiling coming across every Claude working on this project.
#
# DATE HANDLING (learned the hard way): ConvertFrom-Json turns ISO timestamps into
# [DateTime] objects, and string-formatting those yields CURRENT-culture text
# (en-DE -> "02/08/2026"), while PowerShell's [DateTime] cast parses with
# INVARIANT culture (MM/dd) - so "2 Aug" silently reparsed as "8 Feb", landed in the
# past, and the dedupe state for it was pruned on every run. Every timestamp here is
# therefore kept as a real DateTime or an invariant round-trip ("o") string, and
# never reparsed out of a display string.
#
# Always exits 0. Emits JSON with systemMessage when it has something to say, so the
# warning also lands in the transcript, not just a toast that can be missed.

[CmdletBinding()]
param(
    [int]$Threshold = 90,
    [string]$ConfigRoot = 'E:\Claude\claude-config',
    [int]$StaleMinutes = 180,
    [int]$ThrottleMinutes = 5
)

$ErrorActionPreference = 'Continue'

$statePath = Join-Path $ConfigRoot '.usage-alert-state.json'
$notifier = Join-Path $PSScriptRoot 'notify.ps1'

function Load-State {
    if (Test-Path $statePath) {
        try { return Get-Content $statePath -Raw | ConvertFrom-Json -AsHashtable } catch { }
    }
    return @{}
}

# Culture-invariant, sortable, round-trippable. Used for BOTH the dedupe key and the
# stored value, so nothing ever depends on the machine's date format.
function Get-IsoReset([object]$value) {
    if (-not $value) { return 'unknown' }
    if ($value -is [DateTime]) { return $value.ToString('o', [Globalization.CultureInfo]::InvariantCulture) }
    if ($value -is [DateTimeOffset]) { return $value.UtcDateTime.ToString('o', [Globalization.CultureInfo]::InvariantCulture) }
    $parsed = [DateTime]::MinValue
    if ([DateTime]::TryParse([string]$value, [Globalization.CultureInfo]::InvariantCulture,
            [Globalization.DateTimeStyles]::RoundtripKind, [ref]$parsed)) {
        return $parsed.ToString('o', [Globalization.CultureInfo]::InvariantCulture)
    }
    return [string]$value
}

function Format-Clock([object]$value) {
    if ($value -is [DateTime]) { return $value.ToString('HH:mm') }
    $parsed = [DateTime]::MinValue
    if ([DateTime]::TryParse([string]$value, [Globalization.CultureInfo]::InvariantCulture,
            [Globalization.DateTimeStyles]::RoundtripKind, [ref]$parsed)) {
        return $parsed.ToString('HH:mm')
    }
    return '?'
}

try {
    $state = Load-State
    $alerts = @()
    $lines = @()
    $touched = $false

    # THROTTLE. This runs from the Stop hook, i.e. after every single turn, and a
    # full pass parses four ~63 KB .claude.json files plus a pwsh cold start
    # (measured 7.5s under load). The underlying quota cache only refreshes every
    # few minutes anyway, so checking more often than that buys nothing.
    $stampPath = Join-Path $ConfigRoot '.usage-alert-lastcheck'
    if (-not $env:CLAUDE_USAGE_WATCH_VERBOSE -and (Test-Path $stampPath)) {
        try {
            $since = ((Get-Date) - (Get-Item $stampPath).LastWriteTime).TotalMinutes
            if ($since -lt $ThrottleMinutes) { exit 0 }
        } catch { }
    }
    try { Set-Content $stampPath -Value (Get-Date).ToString('o') -Encoding UTF8 } catch { }

    $profiles = Get-ChildItem $ConfigRoot -Directory -Filter 'config-*' -ErrorAction Stop

    foreach ($prof in $profiles) {
        $cfg = Join-Path $prof.FullName '.claude.json'
        if (-not (Test-Path $cfg)) { continue }

        try { $j = Get-Content $cfg -Raw -ErrorAction Stop | ConvertFrom-Json } catch { continue }

        $cache = $j.cachedUsageUtilization
        if (-not $cache -or -not $cache.utilization) { continue }

        $ageMin = [int]((([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() - [int64]$cache.fetchedAtMs)) / 60000)
        $stale = $ageMin -gt $StaleMinutes

        foreach ($lim in @($cache.utilization.limits)) {
            if ($null -eq $lim.percent) { continue }

            $pct = [int]$lim.percent
            $iso = Get-IsoReset $lim.resets_at
            $staleNote = if ($stale) { "  (cache ${ageMin}m old)" } else { '' }

            $lines += ('{0,-16} {1,-11} {2,3}%  resets {3}{4}' -f `
                $prof.Name, $lim.kind, $pct, (Format-Clock $lim.resets_at), $staleNote)

            if ($pct -lt $Threshold) { continue }

            # One alert per profile+limit+reset-window, so a 91% reading does not
            # re-notify every turn until the window rolls over.
            $key = '{0}|{1}|{2}|{3}' -f $prof.Name, $lim.kind, $iso, $Threshold
            if ($state.ContainsKey($key)) { continue }

            $state[$key] = @{ alertedAt = (Get-Date).ToString('o', [Globalization.CultureInfo]::InvariantCulture)
                              resetsAt  = $iso }
            $touched = $true

            $staleFlag = if ($stale) { " [reading is ${ageMin}m stale]" } else { '' }
            $alerts += ('{0}: {1} at {2}% (resets {3}){4}' -f `
                $prof.Name, $lim.kind, $pct, (Format-Clock $lim.resets_at), $staleFlag)
        }
    }

    if ($touched) {
        # Prune windows that reset over a day ago, reading the stored ISO value -
        # never reparsing a display string out of the key.
        $pruned = @{}
        foreach ($k in $state.Keys) {
            $entry = $state[$k]
            $keep = $true
            $resetIso = $null
            if ($entry -is [hashtable] -or $entry -is [System.Collections.IDictionary]) { $resetIso = $entry['resetsAt'] }
            if ($resetIso) {
                $parsed = [DateTime]::MinValue
                if ([DateTime]::TryParse([string]$resetIso, [Globalization.CultureInfo]::InvariantCulture,
                        [Globalization.DateTimeStyles]::RoundtripKind, [ref]$parsed)) {
                    if ($parsed -lt (Get-Date).AddDays(-1)) { $keep = $false }
                }
            }
            if ($keep) { $pruned[$k] = $entry }
        }
        try { $pruned | ConvertTo-Json -Depth 5 | Set-Content $statePath -Encoding UTF8 } catch { }
    }

    if ($alerts.Count) {
        $msg = ($alerts -join ' | ')
        if (Test-Path $notifier) {
            & pwsh -NoProfile -File $notifier -Title "Claude usage >= $Threshold%" -Message $msg 2>$null
        }
        @{ systemMessage = "USAGE WARNING - $msg" } | ConvertTo-Json -Compress
    }
    elseif ($env:CLAUDE_USAGE_WATCH_VERBOSE) {
        # Manual/diagnostic run: show the table even when nothing crosses.
        $lines -join "`n"
    }
}
catch {
    if ($env:CLAUDE_USAGE_WATCH_VERBOSE) { "usage-watch error: $($_.Exception.Message)" }
}

exit 0
