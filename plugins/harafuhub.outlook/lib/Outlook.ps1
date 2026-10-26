# Classic Outlook: finding the mail an index row stands for, and the command
# line that shows it. The index's mapi16:// URL cannot be opened directly
# (a shell namespace, not a command), so the plugin finds the item over COM
# and hands WinShun `OUTLOOK.EXE /select outlook:<EntryID>` to start: WinShun
# is in front when Enter is pressed, so Outlook may come to the front too.

function Get-OutlookExe {
    $key = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\OUTLOOK.EXE'
    $exe = $null
    try { $exe = (Get-ItemProperty $key -ErrorAction Stop).'(default)' } catch { }
    if ($exe -and (Test-Path $exe)) { $exe } else { 'outlook.exe' }
}

function ConvertTo-OutlookFolderPath([string] $IndexFolder) {
    # The index's /store/folder/sub → Outlook's \\store\folder\sub.
    '\\' + ($IndexFolder.Trim('/') -replace '/', '\')
}

function Get-OutlookSelectArgs([string] $Target) {
    # /select takes outlook:<EntryID> or outlook:\\store\folder.
    "/select `"outlook:$Target`""
}

function Get-OutlookApp {
    # The running Outlook, else one started over COM (no window until /select).
    try { return [Runtime.InteropServices.Marshal]::GetActiveObject('Outlook.Application') } catch { }
    New-Object -ComObject Outlook.Application
}

function Get-OutlookFolder($App, [string] $IndexFolder) {
    $parts = @($IndexFolder.Trim('/').Split('/') | Where-Object { $_ })
    if ($parts.Count -eq 0) { throw "No folder in '$IndexFolder'" }
    try {
        $folder = $App.Session.Folders.Item($parts[0])
        foreach ($p in ($parts | Select-Object -Skip 1)) { $folder = $folder.Folders.Item($p) }
    } catch {
        throw "Folder not found in Outlook: $IndexFolder"
    }
    $folder
}

function Find-OutlookMail {
    <#
    The mail in the index folder received at DateUtc (±1 minute; DASL
    compares in UTC) whose subject is Subject. When the subject differs
    but only one mail has that time, that one. $null when none.
    #>
    param($App, [string] $IndexFolder, [datetime] $DateUtc, [string] $Subject)
    $folder = Get-OutlookFolder $App $IndexFolder
    $inv = [Globalization.CultureInfo]::InvariantCulture
    $lo = $DateUtc.AddMinutes(-1).ToString('yyyy-MM-dd HH:mm', $inv)
    $hi = $DateUtc.AddMinutes(1).ToString('yyyy-MM-dd HH:mm', $inv)
    $filter = "@SQL=`"urn:schemas:httpmail:datereceived`" >= '$lo' AND `"urn:schemas:httpmail:datereceived`" <= '$hi'"
    $hits = $folder.Items.Restrict($filter)
    $first = $null
    foreach ($item in $hits) {
        if ($null -eq $first) { $first = $item }
        if ([string]$item.Subject -eq $Subject) { return $item }
    }
    if ($hits.Count -eq 1) { return $first }
    $null
}

function Get-OutlookMailSubject([string] $AttachmentSubject, [string] $Name) {
    # The index gives an attachment the subject "<file name> (<mail subject>)".
    $prefix = "$Name ("
    if ($AttachmentSubject.StartsWith($prefix) -and $AttachmentSubject.EndsWith(')')) {
        return $AttachmentSubject.Substring($prefix.Length, $AttachmentSubject.Length - $prefix.Length - 1)
    }
    ''
}

function Get-OutlookAttachmentRoot { Join-Path $env:TEMP 'harafuhub.outlook' }

function Clear-OutlookAttachments {
    <# Removes the attachments saved more than a day ago (one folder per save). #>
    param([string] $Root = (Get-OutlookAttachmentRoot))
    if (-not (Test-Path $Root)) { return }
    $cutoff = (Get-Date).AddDays(-1)
    Get-ChildItem $Root -Directory | Where-Object { $_.CreationTime -lt $cutoff } |
        ForEach-Object { try { Remove-Item $_.FullName -Recurse -Force -ErrorAction Stop } catch { } }
}

function Save-OutlookAttachment {
    <#
    Saves the attachment Name of the mail found by Find-OutlookMail into a
    new folder under Root (the file keeps its name, so the program that
    opens it shows it) and returns the file's path. Throws when the mail or
    the attachment is not there.
    #>
    param($App, [string] $IndexFolder, [datetime] $DateUtc, [string] $MailSubject, [string] $Name,
        [string] $Root = (Get-OutlookAttachmentRoot))
    $mail = Find-OutlookMail $App $IndexFolder $DateUtc $MailSubject
    if ($null -eq $mail) { throw "Mail not found in Outlook (moved or deleted?)" }
    $attachment = $null
    foreach ($a in $mail.Attachments) {
        if ([string]$a.FileName -eq $Name -or [string]$a.DisplayName -eq $Name) { $attachment = $a; break }
    }
    if ($null -eq $attachment) { throw "Attachment $Name not found in the mail" }
    Clear-OutlookAttachments -Root $Root
    $dir = Join-Path $Root ((Get-Date).ToString('yyyyMMdd-HHmmss-') + [guid]::NewGuid().ToString('N').Substring(0, 6))
    New-Item -ItemType Directory -Force $dir | Out-Null
    $path = Join-Path $dir $Name
    $attachment.SaveAsFile($path)
    $path
}
