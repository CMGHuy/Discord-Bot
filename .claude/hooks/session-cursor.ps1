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
            Where-Object { $_.Name -notmatch '_\d+\.md$|_0-index\.md$' } |
            Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($plan) {
        $n = @(Select-String -Path $plan.FullName -Pattern '^### Task ' -ErrorAction SilentlyContinue).Count
        Emit ("PLAN     : {0} ({1} tasks, {2} KB - grep one task, never read whole)" -f $plan.Name, $n, [int]($plan.Length / 1KB))
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
}
catch {
    Emit "(session-cursor hook error: $($_.Exception.Message))"
}

$out -join "`n"
exit 0
