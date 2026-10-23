# 结束进程 · Kill process: a resident Win顺 plugin in Windows PowerShell on
# the WinShun.psm1 SDK. `kill <name or PID>` lists the processes so named
# (biggest first); Enter ends one, Ctrl+Enter ends it with its children.
# Saved as UTF-8 with a BOM, as every .ps1 for Windows PowerShell 5.1 must be.
Import-Module "$PSScriptRoot\WinShun.psm1"

# Processes Windows runs for itself: listed only when the setting says so.
$systemNames = @('svchost', 'csrss', 'wininit', 'winlogon', 'lsass', 'services', 'smss', 'fontdrvhost', 'dwm', 'sihost',
    'taskhostw', 'RuntimeBroker', 'conhost', 'ctfmon', 'SearchHost', 'StartMenuExperienceHost', 'ShellExperienceHost',
    'TextInputHost', 'SecurityHealthService', 'MsMpEng', 'NisSrv', 'audiodg', 'dllhost', 'WmiPrvSE', 'spoolsv', 'Memory Compression',
    'Registry', 'System', 'Idle', 'LsaIso', 'SgrmBroker', 'dasHost', 'WUDFHost', 'backgroundTaskHost')

Start-WinShunPlugin -Name 'winshun.kill' -OnQuery {
    param($q, $plugin)
    $text = $q.text.Trim()
    $settings = $plugin.settings
    $showSystem = [bool]$settings.showSystem
    $max = if ($settings.maxRows -and [int]$settings.maxRows -gt 0) { [int]$settings.maxRows } else { 30 }
    # By name (or PID) only: a window title or a path is read for the rows
    # shown, never for every process (that takes seconds).
    $procs = Get-Process | Where-Object { $_.Id -ne $PID -and $_.Id -ne 0 }
    if ($text -match '^\d+$') {
        $procs = $procs | Where-Object { $_.Id -eq [int]$text }
    } elseif ($text -ne '') {
        $procs = $procs | Where-Object { $_.ProcessName -like "*$text*" }
    }
    if (-not $showSystem -and $text -eq '') {
        $procs = $procs | Where-Object { $systemNames -notcontains $_.ProcessName }
    }
    $items = @()
    $n = 0
    foreach ($p in ($procs | Sort-Object WorkingSet64 -Descending | Select-Object -First $max)) {
        # The path cannot be read from here (the plugin runs as the user, not
        # as administrator) when the process is elevated, protected or
        # another user's: ending it would fail too, so the row says so.
        $path = $null
        try { $path = $p.Path } catch { }
        $icon = if ($path) { "file:$path" } else { 'glyph:U+E7F8' }
        $mb = [int]($p.WorkingSet64 / 1MB)
        $subtitle = "PID $($p.Id) · $mb MB"
        $title = ''
        try { $title = $p.MainWindowTitle } catch { }
        if ($title) { $subtitle += " · $title" }
        if (-not $path) {
            $cannot = if ($plugin.locale -eq 'en') { 'cannot be ended: elevated or system process' } else { '无权结束：管理员或系统进程' }
            $subtitle += " · $cannot"
        } elseif (-not $title) { $subtitle += " · $path" }
        $items += New-WinShunItem -Id "pid-$($p.Id)" -Title $p.ProcessName -Subtitle $subtitle -Icon $icon -Copy "$($p.Id)" `
            -Score (90 - $n) -Match "$($p.ProcessName) $($p.Id) $title" -Data @{ pid = $p.Id; path = $path }
        $n++
    }
    if ($items.Count -eq 0) {
        $none = if ($plugin.locale -eq 'en') { "No process named $text" } else { "没有叫 $text 的进程" }
        $items += New-WinShunItem -Id 'none' -Title $none -Icon 'glyph:U+E711' -Invalid
    }
    $items
} -OnAction {
    param($a, $plugin)
    $target = [int]$a.item.data.pid
    $title = [string]$a.item.title
    $en = $plugin.locale -eq 'en'
    $denied = $false # access denied: it runs as administrator (or is protected), and the plugin does not
    try {
        if ($a.action -eq 'killTree') {
            $output = taskkill /PID $target /T /F 2>&1 | Out-String
            if ($LASTEXITCODE -ne 0) {
                if ($output -match 'denied|拒绝') { $denied = $true }
                throw "taskkill $LASTEXITCODE"
            }
        } else {
            Stop-Process -Id $target -Force -ErrorAction Stop
        }
        $done = if ($en) { "Ended $title" } else { "已结束 $title" }
        @((New-WinShunEffect -Notify $done), (New-WinShunEffect -Hide))
    } catch {
        $inner = $_.Exception.InnerException
        if ($inner -is [ComponentModel.Win32Exception] -and $inner.NativeErrorCode -eq 5) { $denied = $true }
        elseif ($_.CategoryInfo.Category -eq 'PermissionDenied') { $denied = $true }
        $why = if ($denied) {
            if ($en) { "${title} runs as administrator; the plugin cannot end it" } else { "${title} 以管理员身份运行，插件结束不了" }
        } elseif ($en) { "Could not end ${title}: $($_.Exception.Message)" } else { "没有结束 ${title}：$($_.Exception.Message)" }
        @((New-WinShunEffect -Notify $why), (New-WinShunEffect -Keep))
    }
}
