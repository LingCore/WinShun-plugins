# Outlook mail search: a resident WinShun plugin in Windows PowerShell on the
# WinShun.psm1 SDK. `ol <words>` searches the mails classic Outlook keeps in
# its PST/OST files, and their PDF, Word and Excel attachments by content,
# through the Windows Search index. On a mail Enter opens it in Outlook,
# Ctrl+Enter copies subject and sender, Shift+Enter shows its folder; on an
# attachment Enter opens the file, Shift+Enter its mail.
# Saved as UTF-8 with a BOM, as every .ps1 for Windows PowerShell 5.1 must be.
Import-Module "$PSScriptRoot\WinShun.psm1"
. "$PSScriptRoot\lib\Query.ps1"
. "$PSScriptRoot\lib\Index.ps1"
. "$PSScriptRoot\lib\Rows.ps1"
. "$PSScriptRoot\lib\Outlook.ps1"

function Get-ItemDateUtc($Data) {
    # PowerShell 7's ConvertFrom-Json turns the ISO string into a date already; 5.1 does not.
    if ($Data.utc -is [datetime]) { return $Data.utc.ToUniversalTime() }
    [datetime]::Parse([string]$Data.utc, [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::RoundtripKind)
}

Start-WinShunPlugin -Name 'harafuhub.outlook' -OnQuery {
    param($q, $plugin)
    $settings = $plugin.settings
    $locale = $plugin.locale
    $text = $q.text.Trim()
    $max = if ($settings.maxRows -and [int]$settings.maxRows -gt 0) { [int]$settings.maxRows } else { 50 }
    if ($text -eq '') { $max = [Math]::Min($max, 20) }
    $max = [Math]::Min($max, [Math]::Min([int]$q.limit, 200))
    $attachments = $settings.attachments -ne $false
    $defaultSort = if ($settings.sort) { [string]$settings.sort } else { 'new' }
    # WinShun 0.15+ sends the search panel's filters; older versions send none.
    $query = Add-OutlookPanelFilters (ConvertTo-OutlookQuery $text) $q.filters
    if ($query.NoMatch) {
        return @(New-OutlookMessageItem -Id 'none' -Title (Get-OutlookText $locale 'No mails match these filters' '没有符合筛选条件的邮件'))
    }
    $sort = if ($query.Sort) { $query.Sort } else { $defaultSort }
    $sql = New-OutlookSql $query -Max $max -IncludeOther:([bool]$settings.includeOther) -Attachments:$attachments -Sort $defaultSort
    $sw = [Diagnostics.Stopwatch]::StartNew()
    try {
        $rows = @(Sort-OutlookRows @(Search-OutlookIndex $sql) $sort $max)
        # WinShun asks once per key and the plugin answers in turn: a slow query delays all that follow.
        if ($sw.ElapsedMilliseconds -gt 1000) { Write-WinShunDebug "harafuhub.outlook: slow query ($($sw.ElapsedMilliseconds) ms): $sql" }
    } catch {
        Write-WinShunDebug "harafuhub.outlook: index query failed: $($_.Exception.Message) | $sql"
        return @(New-OutlookMessageItem -Id 'unavailable' `
            -Title (Get-OutlookText $locale 'Windows Search is not available' 'Windows 搜索不可用') `
            -Subtitle $_.Exception.Message)
    }
    if ($rows.Count -eq 0) {
        return @(New-OutlookMessageItem -Id 'none' -Title (Get-OutlookText $locale 'No mails found' '没有找到邮件'))
    }
    $items = @()
    $n = 0
    foreach ($r in $rows) { $items += ConvertTo-OutlookItem $r $n $locale; $n++ }
    $items
} -OnAction {
    param($a, $plugin)
    $locale = $plugin.locale
    $data = $a.item.data
    $exe = Get-OutlookExe
    $isAttachment = [string]$data.kind -eq 'attachment'
    switch ($a.action) {
        'copy' {
            return @((New-WinShunEffect -Copy ([string]$a.item.copy)),
                (New-WinShunEffect -Notify (Get-OutlookText $locale 'Copied' '已复制')), (New-WinShunEffect -Hide))
        }
        'folder' {
            $selectArgs = Get-OutlookSelectArgs (ConvertTo-OutlookFolderPath ([string]$data.folder))
            return @(@{ type = 'open'; path = $exe; args = $selectArgs }, (New-WinShunEffect -Hide))
        }
        default {
            # 'open' (a mail, or an attachment's file) and 'mail' (an attachment's mail).
            try {
                if (-not $data.utc) { throw (Get-OutlookText $locale 'This item has no date to find it by' '这一项没有日期，找不到') }
                $utc = Get-ItemDateUtc $data
                if ($isAttachment -and $a.action -ne 'mail') {
                    $path = Save-OutlookAttachment (Get-OutlookApp) ([string]$data.folder) $utc ([string]$data.subject) ([string]$data.name)
                    return @((New-WinShunEffect -OpenPath $path), (New-WinShunEffect -Hide))
                }
                $mail = Find-OutlookMail (Get-OutlookApp) ([string]$data.folder) $utc ([string]$data.subject)
                if ($null -eq $mail) { throw (Get-OutlookText $locale 'Not found in Outlook (moved or deleted?)' 'Outlook 里没有找到（移走或删除了？）') }
                $selectArgs = Get-OutlookSelectArgs $mail.EntryID
                return @(@{ type = 'open'; path = $exe; args = $selectArgs }, (New-WinShunEffect -Hide))
            } catch {
                Write-WinShunDebug "harafuhub.outlook: open failed: $($_.Exception.Message)"
                return @((New-WinShunEffect -Notify ([string]$_.Exception.Message)), (New-WinShunEffect -Keep))
            }
        }
    }
}
