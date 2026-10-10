# SessionStart hook — prints the real position of the work.
#
# Replaces the hand-maintained "Where things stand" paragraph in CLAUDE.md,
# which drifted 25 tasks stale (claimed ~E22-E27 while E50 was committed).
# Derived state cannot go stale; a prose paragraph can.
#
# Contract: must NEVER fail a session start. Everything is wrapped, and the
# script always exits 0.

$ErrorActionPreference = 'Continue'
Set-Location -LiteralPath $PSScriptRoot\..\..

$out = New-Object System.Collections.ArrayList
function Emit($s) { [void]$out.Add($s) }

try {
    # --- plan cursor: last line of the SDD ledger (173 KB; never read whole) ---
    $cursor = '(progress.md not found)'
    $ledger = '.superpowers/sdd/progress.md'
    if (Test-Path $ledger) {
        # Scan back through the tail rather than reading only the final line: the
        # ledger also carries free-text notes (incident write-ups, corrections), and
        # those are not the cursor. Take the newest line that names a task.
        $tail = @(Get-Content $ledger -Tail 25)
        $taskLine = $null
        for ($i = $tail.Count - 1; $i -ge 0; $i--) {
            if ($tail[$i] -match '^Task ([A-Z]*\d+):\s*(\w+)') { $taskLine = $tail[$i]; break }
        }
        if ($taskLine -match '^Task ([A-Z]*\d+):\s*(\w+)') {
            $id = $Matches[1]; $state = $Matches[2]
            $num = [int]($id -replace '\D', '')
            $prefix = ($id -replace '\d', '')
            $cursor = "$id $state -> next $prefix$($num + 1)"
            if ($tail[-1] -ne $taskLine) { $cursor += '  (ledger tail has later free-text notes - read them)' }
        }
        elseif ($tail.Count) {
            $l = $tail[-1]
            $cursor = $l.Substring(0, [Math]::Min(90, $l.Length))
        }
    }
    Emit "CURSOR   : $cursor"

    # --- active plan: most recently modified plan file, task count ---
    $plan = Get-ChildItem 'docs/superpowers/plans/*.md' -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -notmatch '_\d+[a-z]?(-[^.]*)?\.md$' } |
            Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($plan) {
        $n = @(Select-String -Path $plan.FullName -Pattern '^### Task ' -ErrorAction SilentlyContinue).Count
        Emit ("PLAN     : {0} ({1} tasks, {2} KB - grep one task, never read whole)" -f $plan.Name, $n, [int]($plan.Length / 1KB))
    }

    # --- unfinished plans: ledger ids with no ### Task on disk yet ---
    # A plan cut off by tokens is resumed by whichever session (or account, or
    # Codex) starts next, so the state is derived from the plan files, which all
    # of them share. Plans without a "## Task ledger" (pre-two-phase) are skipped.
    try {
        $pdir = if ($env:SWINGBOT_PLANS_DIR) { $env:SWINGBOT_PLANS_DIR } else { 'docs/superpowers/plans' }
        $groups = Get-ChildItem -LiteralPath $pdir -Filter '*.md' -File -ErrorAction SilentlyContinue |
                  Group-Object { $_.Name -replace '_\d+[a-z]?(-[^.]*)?\.md$', '' -replace '\.md$', '' }
        foreach ($g in $groups) {
            $ledger = New-Object System.Collections.ArrayList
            $written = @{}
            $handoff = $null
            foreach ($f in ($g.Group | Sort-Object Name)) {
                $section = ''
                foreach ($line in (Get-Content -LiteralPath $f.FullName)) {
                    if ($line -match '^## (.+)$') { $section = $Matches[1].Trim(); if ($section -eq 'Handoff') { $handoff = $f.Name } }
                    elseif ($section -eq 'Task ledger' -and $line -match '^\|\s*`?([A-Z][A-Za-z0-9-]*\d[a-z]?)`?\s*\|') { [void]$ledger.Add($Matches[1]) }
                    if ($line -match '^### Task ([A-Za-z0-9-]+)') { $written[$Matches[1].TrimEnd(':')] = $true }
                }
            }
            if ($ledger.Count -eq 0) { continue }
            $missing = @($ledger | Where-Object { -not $written.ContainsKey($_) })
            if ($missing.Count -eq 0) { continue }
            $span = if ($missing.Count -gt 1) { "$($missing[0])..$($missing[-1])" } else { $missing[0] }
            Emit ("PLAN WIP : {0} -- {1}/{2} tasks written, missing {3}" -f $g.Name, ($ledger.Count - $missing.Count), $ledger.Count, $span)
            Emit  "           Resume it before any new plan: plan-writer mode=part <N> per incomplete part, at most 2 at once (skills-tools.md, Plan writing)."
            if ($handoff) { Emit "           Handoff notes: '## Handoff' in $handoff - read them first." }
        }
    }
    catch {
        Emit "PLAN WIP : (check failed: $($_.Exception.Message))"
    }

    # --- git ---
    $head = (git log --oneline -1 2>$null)
    $branch = (git rev-parse --abbrev-ref HEAD 2>$null)
    $dirty = @(git status --porcelain 2>$null)
    Emit "GIT      : $branch @ $head"
    if ($dirty.Count) {
        $names = ($dirty | ForEach-Object { ($_ -replace '^.{3}', '') } | Select-Object -First 6) -join ', '
        Emit "DIRTY    : $($dirty.Count) file(s): $names"
    }

    # --- concurrency guard: another session's long run in flight? ---
    # This trap has already cost a session: a 3-hour walk-forward run was live
    # while a new session started, and running the suite would have contended.
    $busy = Get-Process python -ErrorAction SilentlyContinue |
            Where-Object { $_.CPU -gt 300 } |
            Sort-Object CPU -Descending | Select-Object -First 1
    if ($busy) {
        $mins = [int](((Get-Date) - $busy.StartTime).TotalMinutes)
        Emit "WARNING  : python PID $($busy.Id) running ${mins}m ($([int]$busy.CPU)s CPU) - likely another session's backtest."
        Emit "           Do not run the full suite or a backtest script until it finishes."
        $log = Get-ChildItem 'docs/superpowers/results/*.log' -ErrorAction SilentlyContinue |
               Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if ($log -and $log.LastWriteTime -gt (Get-Date).AddMinutes(-30)) {
            Emit "           Live log: $($log.Name) - $(Get-Content $log.FullName -Tail 1)"
        }
    }

    $wt = @(git worktree list 2>$null)
    if ($wt.Count -gt 1) { Emit "WORKTREES: $($wt.Count - 1) extra (excluded from search by .ignore; never edit from here)" }

    # --- off-VM backup: age of the last good pull (spec v120 s2) ---
    # Own try/catch: a bad file prints the warning and never throws.
    try {
        # The off-VM copy lives in the MAIN worktree's backups/, so a session in a
        # worktree sees the same pulls (and removing the worktree cannot delete them).
        $bdir = 'backups'
        # git older than 2.31 rejects --path-format and prints extra lines: take the last.
        $common = (git rev-parse --path-format=absolute --git-common-dir 2>$null) | Select-Object -Last 1
        if (($common -is [string]) -and $common -and (Test-Path -LiteralPath $common -PathType Container)) {
            $bdir = Join-Path (Split-Path -Parent $common) 'backups'
        }
        if ($env:SWINGBOT_BACKUPS_DIR) { $bdir = $env:SWINGBOT_BACKUPS_DIR }
        $goodFile = Join-Path $bdir 'LAST_GOOD_PULL'
        $days = $null
        if (Test-Path -LiteralPath $goodFile) {
            $first = ((Get-Content -LiteralPath $goodFile -TotalCount 1) -split '\s+')[0]
            $when = [DateTimeOffset]::Parse($first, [Globalization.CultureInfo]::InvariantCulture,
                                            [Globalization.DateTimeStyles]::AssumeUniversal)
            $days = [int][Math]::Max(0, [Math]::Floor(([DateTimeOffset]::UtcNow - $when).TotalDays))
            $folder = ((Get-Content -LiteralPath $goodFile -TotalCount 1) -split '\s+')[1]
            $folderMissing = (-not $folder) -or -not (Test-Path -LiteralPath (Join-Path $bdir $folder) -PathType Container)
        }
        if ($null -eq $days) {
            Emit "BACKUP   : WARNING no good pull yet -- run /backup-pull"
        }
        elseif ($folderMissing) {
            Emit "BACKUP   : WARNING last good pull folder is missing -- run /backup-pull"
        }
        elseif ($days -gt 7) {
            Emit "BACKUP   : WARNING no good pull for ${days}d -- run /backup-pull"
        }
        else {
            $stable = Get-ChildItem -LiteralPath (Join-Path $bdir 'stable') -Directory -ErrorAction SilentlyContinue |
                      Where-Object { $_.Name -notlike '*.partial' } |
                      Sort-Object Name | Select-Object -Last 1
            $sname = if ($stable) { $stable.Name } else { 'none' }
            Emit "BACKUP   : last good pull ${days}d ago | newest stable $sname"
        }
    }
    catch {
        Emit "BACKUP   : WARNING no good pull yet (unreadable LAST_GOOD_PULL) -- run /backup-pull"
    }
}
catch {
    Emit "(session-cursor hook error: $($_.Exception.Message))"
}

$out -join "`n"
exit 0
