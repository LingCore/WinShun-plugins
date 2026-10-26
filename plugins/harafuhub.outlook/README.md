# Outlook mail · harafuhub.outlook

A resident WinShun plugin in Windows PowerShell. `ol <words>` (or `mail <words>`) searches the
mail classic Outlook keeps in its PST/OST files, through the Windows Search index that Outlook
already maintains: results in milliseconds, Outlook need not be running, nothing goes online.

| Type | Finds |
|---|---|
| `ol` | the 20 newest mails |
| `ol rechnung müller` | mails with words starting `rechnung` and `müller` (subject, body, sender, attachment names) |
| `ol "booking confirmation"` | the exact phrase |
| `ol from:anna` · `ol to:bob` | sender, or a To/Cc recipient |
| `ol in:done` | folder path contains a word starting `done` |
| `ol has:att` | only mails with attachments (and matching attachments) |
| `ol type:pdf rechnung` | only PDF attachments containing `rechnung*` (`type:xlsx,docx`, `doc`, `xls` too) |
| `ol … sort:old` | order: `new` (default), `old`, `size`, `from`, `subject` |
| `ol … date:7d` | received: `today`, `yesterday`, `week`, `month`, `year`, `<n>d`, or a year / month / day: `2026`, `2026-10`, `2026-10-21`, `21.10.2026` |
| `ol … after:2026-10-01 before:15.10.2026` | received from / before a date (same forms) |
| `ol … size:>1mb` | size: `>1mb`, `<500kb`, `1mb-100mb` (no unit: MB) |

**WinShun 0.15+ search panel (Ctrl+E):** every row carries its received date (Date modified and
Created columns) and size, so the columns show, sort and filter mail and attachments. The panel's
Date modified, Size and file type / Documents filters go straight into the index query (with
`date:`/`size:` typed as well, the narrower bound wins). Older WinShun versions ignore all this;
there `date:`, `size:` and `type:` do the filtering.

With words to search for, matching **attachments** (PDF, DOCX, XLSX, DOC, XLS: name and
content) are listed beside the mails, each as its own row with a file icon (Settings: off).

On a mail: **Enter** opens it in Outlook · **Ctrl+Enter** copies subject and sender ·
**Shift+Enter** shows its folder in Outlook. On an attachment: **Enter** saves it to
`%TEMP%\harafuhub.outlook` (cleared after a day) and opens it · **Ctrl+Enter** copies the file name ·
**Shift+Enter** opens its mail. Hovering a row shows the start of the text.

`sort:from` and `sort:subject` order the 200 newest matches (the index takes seconds to sort a
whole mailbox by them); the other orders cover every match.

How opening works: the index's `mapi16://` address cannot be started directly, so the plugin
finds the mail over Outlook COM (folder from the index, received time and subject) and asks
WinShun to start `OUTLOOK.EXE /select outlook:<EntryID>`. When Outlook is closed, the first
Enter starts it in the background, which takes a few seconds.

**Permissions: none.** What it touches, all on this PC as you:

- reads the Windows Search index (OLE DB, `Search.CollatorDSO`), read-only;
- talks to classic Outlook over COM to find a mail (starting Outlook in the background if it is
  closed) and asks WinShun to start `OUTLOOK.EXE /select …` to show it;
- writes an attachment you open to `%TEMP%\harafuhub.outlook\` and deletes those copies after a day;
- never goes online; nothing is sent anywhere.

Needs: classic Outlook (Microsoft 365 / 2016+) with Windows Search indexing its mail
(Outlook → File → Options → Search → Indexing Options). The new Outlook keeps no PST/OST and is
not searched.

Settings: attachments (on); default order (newest first); rows at most (50); also calendar,
contacts and tasks (off; these only open their folder).
