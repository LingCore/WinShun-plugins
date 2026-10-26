# The Windows Search index over OLE DB: Outlook indexes every PST/OST it has
# open, so the mails are searched here without Outlook running.

$script:IndexConnection = $null

function Get-IndexConnection {
    if ($null -eq $script:IndexConnection -or $script:IndexConnection.State -ne 1) {
        $c = New-Object -ComObject ADODB.Connection
        $c.Open("Provider=Search.CollatorDSO;Extended Properties='Application=Windows';")
        $script:IndexConnection = $c
    }
    $script:IndexConnection
}

function Close-IndexConnection {
    if ($null -ne $script:IndexConnection) {
        try { $script:IndexConnection.Close() } catch { }
        $script:IndexConnection = $null
    }
}

function Get-FieldValue($Fields, [string] $Name) {
    $v = $Fields.Item($Name).Value
    if ($v -is [DBNull]) { $null } else { $v }
}

function Invoke-IndexSql([string] $Sql) {
    $rs = (Get-IndexConnection).Execute($Sql)
    try {
        while (-not $rs.EOF) {
            $f = $rs.Fields
            # The index keeps dates in UTC but hands them back unmarked.
            $utc = $null
            $date = $null
            $received = Get-FieldValue $f 'System.Message.DateReceived'
            if ($received -is [datetime]) {
                $utc = [datetime]::SpecifyKind($received, [DateTimeKind]::Utc)
                $date = $utc.ToLocalTime()
            }
            $url = [string](Get-FieldValue $f 'System.ItemUrl')
            $size = Get-FieldValue $f 'System.Size'
            [pscustomobject]@{
                Url = $url
                # An attachment's address is its mail's plus /at=<id>:<file name>.
                IsAttachment = $url -match '/at=[^/]*$'
                Name = [string](Get-FieldValue $f 'System.ItemName')
                Size = if ($null -ne $size) { [long]$size } else { 0 }
                Subject = [string](Get-FieldValue $f 'System.Subject')
                FromName = [string](Get-FieldValue $f 'System.Message.FromName')
                FromAddress = [string](Get-FieldValue $f 'System.Message.FromAddress')
                DateUtc = $utc
                Date = $date
                HasAttachments = [bool](Get-FieldValue $f 'System.Message.HasAttachments')
                Folder = [string](Get-FieldValue $f 'System.ItemFolderPathDisplay')
                Summary = [string](Get-FieldValue $f 'System.Search.AutoSummary')
            }
            $rs.MoveNext()
        }
    } finally {
        try { $rs.Close() } catch { }
    }
}

function Search-OutlookIndex {
    <#
    Runs a SystemIndex query (New-OutlookSql) and returns one object per
    item: Url, IsAttachment, Name, Size, Subject, FromName, FromAddress,
    DateUtc, Date (local), HasAttachments, Folder (/store/folder/…), Summary.
    An attachment carries its mail's sender, date and folder; its Subject is
    "<file name> (<mail subject>)". A dropped connection
    is opened again once; a second failure throws.
    #>
    param([Parameter(Mandatory = $true)] [string] $Sql)
    try {
        @(Invoke-IndexSql $Sql)
    } catch {
        Close-IndexConnection
        @(Invoke-IndexSql $Sql)
    }
}
