# Index rows (Search-OutlookIndex) as WinShun result rows.

function Get-OutlookText([string] $Locale, [string] $En, [string] $Zh) {
    if ($Locale -eq 'zh') { $Zh } else { $En }
}

function Get-OutlookMetadata($Row) {
    # For WinShun 0.15+'s Date modified / Created / Size columns, sort and filters: received date (UTC) and size.
    $meta = @{}
    if ($Row.DateUtc) { $stamp = $Row.DateUtc.ToString('yyyy-MM-ddTHH:mm:ssZ'); $meta.Modified = $stamp; $meta.Created = $stamp }
    if ($Row.Size -gt 0) { $meta.Size = [long]$Row.Size }
    $meta
}

function Format-OutlookSize([long] $Bytes) {
    if ($Bytes -ge 1MB) { '{0:0.#} MB' -f ($Bytes / 1MB) } elseif ($Bytes -ge 1KB) { '{0:0} KB' -f ($Bytes / 1KB) } else { "$Bytes B" }
}

function ConvertTo-OutlookAttachmentItem {
    <#
    One attachment as a WinShun item: Enter opens the file, Ctrl+Enter
    copies its name, Shift+Enter opens the mail it came with.
    #>
    param([Parameter(Mandatory = $true)] $Row, [int] $Rank = 0, [string] $Locale = 'en')
    $mailSubject = Get-OutlookMailSubject $Row.Subject $Row.Name
    $sender = if ($Row.FromName) { $Row.FromName } else { $Row.FromAddress }
    $parts = @()
    if ($sender) { $parts += $sender }
    if ($Row.Date) { $parts += $Row.Date.ToString('g') }
    if ($mailSubject) { $parts += $mailSubject }
    if ($Row.Size -gt 0) { $parts += Format-OutlookSize $Row.Size }
    $ext = [IO.Path]::GetExtension($Row.Name).TrimStart('.').ToLowerInvariant()
    $preview = $null
    if ($Row.Summary) {
        $preview = ($Row.Summary -replace '\s+', ' ').Trim()
        if ($preview.Length -gt 300) { $preview = $preview.Substring(0, 300) + '…' }
    }
    $data = @{ kind = 'attachment'; folder = $Row.Folder; subject = $mailSubject; name = $Row.Name }
    if ($Row.DateUtc) { $data.utc = $Row.DateUtc.ToString('o') }
    $actions = @(
        (New-WinShunAction -Id 'open' -Title (Get-OutlookText $Locale 'Open attachment' '打开附件') -Key 'Enter'),
        (New-WinShunAction -Id 'copy' -Title (Get-OutlookText $Locale 'Copy file name' '复制文件名') -Key 'Ctrl+Enter'),
        (New-WinShunAction -Id 'mail' -Title (Get-OutlookText $Locale 'Open its mail in Outlook' '在 Outlook 中打开邮件') -Key 'Shift+Enter')
    )
    $meta = Get-OutlookMetadata $Row
    New-WinShunItem -Id $Row.Url -Title $Row.Name -Subtitle ($parts -join ' · ') -Icon "ext:$ext" `
        -Score ([Math]::Max(1, 99 - $Rank)) -Copy $Row.Name -Preview $preview -Data $data -Actions $actions @meta
}

function ConvertTo-OutlookItem {
    <# One mail (or attachment) as a WinShun item; Rank 0 comes first (highest score). #>
    param([Parameter(Mandatory = $true)] $Row, [int] $Rank = 0, [string] $Locale = 'en')
    if ($Row.IsAttachment) { return ConvertTo-OutlookAttachmentItem $Row $Rank $Locale }
    $subject = if ($Row.Subject) { $Row.Subject } else { Get-OutlookText $Locale '(no subject)' '（无主题）' }
    $sender = if ($Row.FromName) { $Row.FromName } else { $Row.FromAddress }
    # /store/Inbox/Done → Inbox/Done; the store alone when that is all.
    $segments = @($Row.Folder.Trim('/').Split('/') | Where-Object { $_ })
    $folder = if ($segments.Count -gt 1) { ($segments | Select-Object -Skip 1) -join '/' } else { $segments -join '/' }

    $parts = @()
    if ($sender) { $parts += $sender }
    if ($Row.Date) { $parts += $Row.Date.ToString('g') }
    if ($folder) { $parts += $folder }
    if ($Row.HasAttachments) { $parts += [char]::ConvertFromUtf32(0x1F4CE) }

    $copy = $subject
    if ($sender) {
        $copy += " — $sender"
        if ($Row.FromAddress -and $Row.FromAddress -ne $sender) { $copy += " <$($Row.FromAddress)>" }
    }
    $preview = $null
    if ($Row.Summary) {
        $preview = ($Row.Summary -replace '\s+', ' ').Trim()
        if ($preview.Length -gt 300) { $preview = $preview.Substring(0, 300) + '…' }
    }
    $data = @{ folder = $Row.Folder; subject = [string]$Row.Subject }
    if ($Row.DateUtc) { $data.utc = $Row.DateUtc.ToString('o') }

    $meta = Get-OutlookMetadata $Row
    New-WinShunItem -Id $Row.Url -Title $subject -Subtitle ($parts -join ' · ') -Icon 'glyph:U+E715' `
        -Score ([Math]::Max(1, 99 - $Rank)) -Copy $copy -Preview $preview -Data $data @meta
}

function New-OutlookMessageItem {
    <# A row that only says something (Enter does nothing). #>
    param([string] $Id, [string] $Title, [string] $Subtitle)
    New-WinShunItem -Id $Id -Title $Title -Subtitle $Subtitle -Icon 'glyph:U+E715' -Invalid
}
