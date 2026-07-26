# Desktop notification helper for Claude Code hooks (Windows).
#
# Usage:
#   notify.ps1 -Title "..." -Message "..."
#   echo '{"message":"..."}' | notify.ps1        # Notification hook form
#
# Uses a NotifyIcon balloon tip: no external module (BurntToast et al.) required,
# and Windows 11 routes it to the normal toast/Action Center surface. Also rings
# the terminal bell so it registers even if the toast is missed.
#
# Must never fail a hook: everything is wrapped, always exits 0.

[CmdletBinding()]
param(
    [string]$Title = 'Claude Code',
    [string]$Message = ''
)

$ErrorActionPreference = 'Continue'

try {
    # Notification-hook payload arrives as JSON on stdin.
    if (-not $Message -and [Console]::IsInputRedirected) {
        $raw = [Console]::In.ReadToEnd()
        if ($raw) {
            try {
                $p = $raw | ConvertFrom-Json
                if ($p.message)      { $Message = $p.message }
                elseif ($p.title)    { $Message = $p.title }
                if ($p.title)        { $Title = "Claude Code - $($p.title)" }
                if ($p.cwd)          { $Title = "Claude Code - $(Split-Path $p.cwd -Leaf)" }
            } catch {
                $Message = $raw.Trim()
            }
        }
    }

    if (-not $Message) { $Message = 'Claude needs your input.' }

    # Balloon tips truncate silently past ~255 chars.
    if ($Message.Length -gt 240) { $Message = $Message.Substring(0, 237) + '...' }

    Add-Type -AssemblyName System.Windows.Forms -ErrorAction Stop
    Add-Type -AssemblyName System.Drawing -ErrorAction Stop

    $icon = New-Object System.Windows.Forms.NotifyIcon
    $icon.Icon = [System.Drawing.SystemIcons]::Information
    $icon.BalloonTipIcon = [System.Windows.Forms.ToolTipIcon]::Info
    $icon.BalloonTipTitle = $Title
    $icon.BalloonTipText = $Message
    $icon.Visible = $true
    $icon.ShowBalloonTip(10000)

    # Give the shell time to pick the balloon up before the icon is disposed.
    Start-Sleep -Milliseconds 900
    $icon.Dispose()

    [Console]::Beep(880, 200)
}
catch {
    # Last resort: bell only. A failed notification must not break the session.
    try { [Console]::Beep(660, 150) } catch { }
}

exit 0
