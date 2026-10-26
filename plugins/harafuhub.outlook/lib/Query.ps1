# What the user typed after `ol`, turned into a Windows Search SQL query.
# Pure functions: no index, no Outlook; tests/Query.Tests.ps1.

# Attachments Outlook indexes by content that `ol` lists beside the mails.
$script:AttachmentTypes = @('pdf', 'docx', 'xlsx', 'doc', 'xls')

$script:SortNames = @{
    new = 'new'; newest = 'new'; old = 'old'; oldest = 'old'; from = 'from'; sender = 'from'
    subject = 'subject'; size = 'size'
}

function ConvertFrom-OutlookDate([string] $Value) {
    # A year, month or day (2026, 2026-10, 2026-10-21, 21.10.2026) as @{ Start; End } in local time; $null when none.
    $inv = [Globalization.CultureInfo]::InvariantCulture
    $d = [datetime]::MinValue
    foreach ($f in 'yyyy-MM-dd', 'dd.MM.yyyy', 'd.M.yyyy') {
        if ([datetime]::TryParseExact($Value, $f, $inv, 'None', [ref]$d)) { return @{ Start = $d; End = $d.AddDays(1) } }
    }
    if ([datetime]::TryParseExact($Value, 'yyyy-MM', $inv, 'None', [ref]$d)) { return @{ Start = $d; End = $d.AddMonths(1) } }
    if ($Value -match '^(19|20)\d\d$') { $d = [datetime]::new([int]$Value, 1, 1); return @{ Start = $d; End = $d.AddYears(1) } }
    $null
}

function ConvertFrom-OutlookSize([string] $Value) {
    # 500kb, 1mb, 1.5gb, 2 (MB when no unit) in bytes; $null when not a size.
    if ($Value -notmatch '^(?<n>\d+(?:\.\d+)?)(?<u>b|kb|mb|gb)?$') { return $null }
    $unit = switch ($Matches['u']) { 'b' { 1 } 'kb' { 1KB } 'gb' { 1GB } default { 1MB } }
    [long]([double]::Parse($Matches['n'], [Globalization.CultureInfo]::InvariantCulture) * $unit)
}

function ConvertTo-OutlookQuery {
    <#
    Splits the text into words (prefix matches), "quoted phrases" and the
    filters from:, to:, in: (a value may be quoted), has:attachment,
    type:pdf,xlsx, sort:new|old|from|subject|size, date:today|yesterday|
    week|month|year|<n>d|<year>|<month>|<day>, after:<date>, before:<date>
    and size:>1mb|<500kb|1mb-100mb. After/Before are local times (Before
    exclusive); WinShun's own date and size filters never reach a plugin,
    so these stand in for them. An unknown prefix such as http: stays a word.
    #>
    param([string] $Text, [datetime] $Now = (Get-Date))
    $q = [pscustomobject]@{
        Terms = @(); Phrases = @(); From = @(); To = @(); In = @(); HasAttachment = $false; Types = @(); Sort = ''
        After = $null; Before = $null; MinSize = $null; MaxSize = $null; NoMatch = $false
    }
    $today = $Now.Date
    $pattern = '(?<key>[A-Za-z]+):"(?<quoted>[^"]*)"?|"(?<phrase>[^"]*)"?|(?<key>[A-Za-z]+):(?<value>\S*)|(?<word>\S+)'
    foreach ($m in [regex]::Matches([string]$Text, $pattern)) {
        if ($m.Groups['phrase'].Success) {
            $p = $m.Groups['phrase'].Value.Trim()
            if ($p) { $q.Phrases += $p }
            continue
        }
        if ($m.Groups['word'].Success) { $q.Terms += $m.Groups['word'].Value; continue }
        $key = $m.Groups['key'].Value.ToLowerInvariant()
        $value = if ($m.Groups['quoted'].Success) { $m.Groups['quoted'].Value } else { $m.Groups['value'].Value }
        $value = $value.Trim()
        switch ($key) {
            'from' { if ($value) { $q.From += $value } }
            'to' { if ($value) { $q.To += $value } }
            'in' { if ($value) { $q.In += $value } }
            'has' {
                if ($value -match '^(?i)att(achments?)?$') { $q.HasAttachment = $true } else { $q.Terms += $m.Value }
            }
            'sort' {
                $name = $value.ToLowerInvariant()
                if ($script:SortNames.ContainsKey($name)) { $q.Sort = $script:SortNames[$name] } else { $q.Terms += $m.Value }
            }
            'type' {
                $types = @($value.ToLowerInvariant().Split(',') | ForEach-Object { $_.Trim().TrimStart('.') } | Where-Object { $_ })
                $known = @($types | Where-Object { $script:AttachmentTypes -contains $_ })
                if ($known.Count -gt 0) { $q.Types += $known } else { $q.Terms += $m.Value }
            }
            'date' {
                $v = $value.ToLowerInvariant()
                $days = if ($v -match '^(\d{1,4})d$') { [int]$Matches[1] } elseif ($v -eq 'week') { 7 } elseif ($v -eq 'month') { 30 } else { 0 }
                if ($v -eq 'today') { $q.After = $today; $q.Before = $today.AddDays(1) }
                elseif ($v -eq 'yesterday') { $q.After = $today.AddDays(-1); $q.Before = $today }
                elseif ($v -eq 'year') { $q.After = [datetime]::new($today.Year, 1, 1) }
                elseif ($days -gt 0) { $q.After = $today.AddDays(1 - $days) }
                else {
                    $range = ConvertFrom-OutlookDate $value
                    if ($range) { $q.After = $range.Start; $q.Before = $range.End } else { $q.Terms += $m.Value }
                }
            }
            'after' {
                $range = ConvertFrom-OutlookDate $value
                if ($range) { $q.After = $range.Start } else { $q.Terms += $m.Value }
            }
            'before' {
                $range = ConvertFrom-OutlookDate $value
                if ($range) { $q.Before = $range.Start } else { $q.Terms += $m.Value }
            }
            'size' {
                $v = $value.ToLowerInvariant()
                $ok = $false
                if ($v -match '^>(.+)$') { $n = ConvertFrom-OutlookSize $Matches[1]; if ($null -ne $n) { $q.MinSize = $n; $ok = $true } }
                elseif ($v -match '^<(.+)$') { $n = ConvertFrom-OutlookSize $Matches[1]; if ($null -ne $n) { $q.MaxSize = $n; $ok = $true } }
                elseif ($v -match '^([^-]+)-([^-]+)$') {
                    $lo = ConvertFrom-OutlookSize $Matches[1]
                    $hi = ConvertFrom-OutlookSize $Matches[2]
                    if ($null -ne $lo -and $null -ne $hi) { $q.MinSize = $lo; $q.MaxSize = $hi; $ok = $true }
                }
                if (-not $ok) { $q.Terms += $m.Value }
            }
            default { $q.Terms += $m.Value }
        }
    }
    $q
}

function Add-OutlookPanelFilters {
    <#
    Narrows a parsed query by the filters of WinShun's search panel (0.15+:
    q.filters with modifiedFrom/modifiedTo as ISO UTC, minSize/maxSize in
    bytes, extensions, kinds). Where the text has a bound too, the narrower
    one wins. Extensions and kinds keep the attachment types they name;
    when they name none (mail has no extension), NoMatch is set.
    #>
    param([Parameter(Mandatory = $true)] $Query, $Filters)
    if ($null -eq $Filters) { return $Query }
    $inv = [Globalization.CultureInfo]::InvariantCulture
    if ($Filters.modifiedFrom) {
        $from = [datetime]::Parse([string]$Filters.modifiedFrom, $inv, [Globalization.DateTimeStyles]::RoundtripKind).ToLocalTime()
        if (-not $Query.After -or $from -gt $Query.After) { $Query.After = $from }
    }
    if ($Filters.modifiedTo) {
        $to = [datetime]::Parse([string]$Filters.modifiedTo, $inv, [Globalization.DateTimeStyles]::RoundtripKind).ToLocalTime()
        if (-not $Query.Before -or $to -lt $Query.Before) { $Query.Before = $to }
    }
    if ($null -ne $Filters.minSize -and ($null -eq $Query.MinSize -or [long]$Filters.minSize -gt $Query.MinSize)) { $Query.MinSize = [long]$Filters.minSize }
    if ($null -ne $Filters.maxSize -and ($null -eq $Query.MaxSize -or [long]$Filters.maxSize -lt $Query.MaxSize)) { $Query.MaxSize = [long]$Filters.maxSize }

    $allowed = $null
    $extensions = @($Filters.extensions | Where-Object { $_ } | ForEach-Object { ([string]$_).ToLowerInvariant().TrimStart('.') })
    if ($extensions.Count -gt 0) { $allowed = @($script:AttachmentTypes | Where-Object { $extensions -contains $_ }) }
    $kinds = @($Filters.kinds | Where-Object { $_ })
    if ($kinds.Count -gt 0) {
        # Plain assignments: `$x = if (…) { @() }` would leave $null, not an empty list.
        $byKind = @()
        if ($kinds -contains 'documents') { $byKind = $script:AttachmentTypes }
        if ($null -eq $allowed) { $allowed = @($byKind) } else { $allowed = @($allowed | Where-Object { $byKind -contains $_ }) }
    }
    if ($null -ne $allowed) {
        if (@($Query.Types).Count -gt 0) { $allowed = @($Query.Types | Where-Object { $allowed -contains $_ }) }
        if ($allowed.Count -eq 0) { $Query.NoMatch = $true } else { $Query.Types = $allowed }
    }
    $Query
}

function ConvertTo-ContainsText([string] $Text) {
    # Inside CONTAINS(…, '"…"'): no double quotes or wildcards of our own; ' doubled for SQL.
    ($Text -replace '["*]', ' ').Trim() -replace "'", "''"
}

function New-OutlookSql {
    <#
    The SystemIndex query for a parsed query (ConvertTo-OutlookQuery).
    Only CONTAINS and SCOPE: a LIKE (even ItemUrl LIKE 'mapi%') makes the
    indexer scan every item, 2–6 s per query on a big mailbox. Ordering by
    sender or subject is as slow, so those fetch the 200 newest and leave
    the order to Sort-OutlookRows. -Attachments lists attachments (by
    content) beside the mails when there are words to search for; -Sort is
    the default order when the query has no sort:.
    #>
    param([Parameter(Mandatory = $true)] $Query, [int] $Max = 50, [switch] $IncludeOther, [switch] $Attachments,
        [string] $Sort = 'new')
    $columns = 'System.ItemUrl, System.ItemName, System.Subject, System.Message.FromName, System.Message.FromAddress, ' +
        'System.Message.DateReceived, System.Message.HasAttachments, System.ItemFolderPathDisplay, System.Size, System.Search.AutoSummary'

    $mailKinds = if ($IncludeOther) {
        "(System.Kind = 'email' OR System.Kind = 'calendar' OR System.Kind = 'contact' OR System.Kind = 'task')"
    } else { "System.Kind = 'email'" }
    if ($Query.HasAttachment) { $mailKinds = "($mailKinds AND System.Message.HasAttachments = TRUE)" }
    $hasWords = @($Query.Terms).Count + @($Query.Phrases).Count -gt 0
    if (@($Query.Types).Count -gt 0) {
        $kinds = '(' + ((@($Query.Types) | ForEach-Object { "System.ItemType = '.$_'" }) -join ' OR ') + ')'
    } elseif ($Attachments -and $hasWords) {
        $kinds = "($mailKinds OR " + (($script:AttachmentTypes | ForEach-Object { "System.ItemType = '.$_'" }) -join ' OR ') + ')'
    } else {
        $kinds = $mailKinds
    }
    # Outlook 2016 and later (Microsoft 365) index under mapi16:, 2013 under mapi15:.
    $where = @("(SCOPE='mapi16:' OR SCOPE='mapi15:')", $kinds)

    foreach ($t in $Query.Terms) {
        $c = ConvertTo-ContainsText $t
        # One letter as a prefix matches most of the mailbox (slow, useless): a whole word only.
        $star = if ($c.Length -gt 1) { '*' } else { '' }
        if ($c -match '[\p{L}\p{N}]') { $where += "CONTAINS(*, '`"$c$star`"')" }
    }
    foreach ($p in $Query.Phrases) {
        $c = ConvertTo-ContainsText $p
        if ($c -match '[\p{L}\p{N}]') { $where += "CONTAINS(*, '`"$c`"')" }
    }
    # Filters match words of the field by prefix: from:example finds info@example.com.
    foreach ($f in $Query.From) {
        $c = ConvertTo-ContainsText $f
        if ($c -match '[\p{L}\p{N}]') {
            $where += "(CONTAINS(System.Message.FromName, '`"$c*`"') OR CONTAINS(System.Message.FromAddress, '`"$c*`"'))"
        }
    }
    foreach ($t in $Query.To) {
        $c = ConvertTo-ContainsText $t
        if ($c -match '[\p{L}\p{N}]') {
            $any = foreach ($col in 'ToName', 'ToAddress', 'CcName', 'CcAddress') { "CONTAINS(System.Message.$col, '`"$c*`"')" }
            $where += '(' + ($any -join ' OR ') + ')'
        }
    }
    foreach ($i in $Query.In) {
        $c = ConvertTo-ContainsText $i
        if ($c -match '[\p{L}\p{N}]') { $where += "CONTAINS(System.ItemFolderPathDisplay, '`"$c*`"')" }
    }
    # The index keeps dates in UTC; After/Before are local.
    $utcFormat = 'yyyy-MM-dd HH:mm:ss'
    $inv = [Globalization.CultureInfo]::InvariantCulture
    if ($Query.After) { $where += "System.Message.DateReceived >= '$(([datetime]$Query.After).ToUniversalTime().ToString($utcFormat, $inv))'" }
    if ($Query.Before) { $where += "System.Message.DateReceived < '$(([datetime]$Query.Before).ToUniversalTime().ToString($utcFormat, $inv))'" }
    if ($null -ne $Query.MinSize) { $where += "System.Size >= $([long]$Query.MinSize)" }
    if ($null -ne $Query.MaxSize) { $where += "System.Size <= $([long]$Query.MaxSize)" }

    $order = if ($Query.Sort) { $Query.Sort } else { $Sort }
    $top = $Max
    $orderBy = switch ($order) {
        'old' { 'System.Message.DateReceived ASC' }
        'size' { 'System.Size DESC' }
        { $_ -in 'from', 'subject' } { $top = [Math]::Max($Max, 200); 'System.Message.DateReceived DESC' }
        default { 'System.Message.DateReceived DESC' }
    }
    "SELECT TOP $top $columns FROM SystemIndex WHERE " + ($where -join ' AND ') + " ORDER BY $orderBy"
}

function Sort-OutlookRows {
    <#
    Puts index rows in sender or subject order (the index takes seconds for
    that) and keeps the first Max; other orders are the index's already.
    #>
    param([array] $Rows, [string] $Sort, [int] $Max)
    $sorted = switch ($Sort) {
        'from' { $Rows | Sort-Object { if ($_.FromName) { $_.FromName } else { $_.FromAddress } }, @{ Expression = 'DateUtc'; Descending = $true } }
        'subject' { $Rows | Sort-Object Subject, @{ Expression = 'DateUtc'; Descending = $true } }
        default { $Rows }
    }
    @($sorted) | Select-Object -First $Max
}
