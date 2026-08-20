## Export the filtered invoice list to a spreadsheet

### Context
Accountants reconcile invoices against their own spreadsheets and currently
re-key the figures by hand, which is slow and introduces transcription errors.
The invoice list screen already supports filtering, so the data they need is on
screen; there is simply no way to get it out. Raised repeatedly by accountants.

### User Story
As an accountant, I want to export the filtered invoice list to a spreadsheet, so that I can reconcile against my own sheet without re-keying.

### Acceptance Criteria
1. **Given** I am signed in as an accountant **When** I choose Export on the invoice list **Then** a spreadsheet file is produced.
2. **Given** I have applied filters to the invoice list **When** I choose Export **Then** the file contains only the rows matching those filters.
3. **Given** the invoice list is showing its columns **When** I choose Export **Then** the file carries the same columns, in the same order as the screen.
4. **Given** the export contains monetary amounts **When** I open the file **Then** every amount carries an explicit currency.
5. **Given** the filtered list contains no invoices **When** I choose Export **Then** I am told there is nothing to export, and no file is produced.

### Technical Hints
- Enforce the export in the Service layer. The Controller passes the existing filter specification through and holds no logic of its own.
- Reuse the specification the list screen already composes, so the filters applied on screen and the filters applied to the export cannot drift apart.
- The repository returns `IQueryable` by design; stream the result rather than materialising the full set in memory.
- Amounts are `decimal` with an explicit `Currency`, never `double`.

### Out of Scope
- Scheduled or recurring exports.
- Exporting from screens other than the invoice list.
- Editing or re-importing the exported file.

### Open Questions
- [ ] @product-owner-a: the input says "excel". Is a CSV acceptable, or is a true `.xlsx` workbook required? These are materially different pieces of work.
- [ ] @product-owner-a: should the export honour the current sort order as well as the active filters?

### Readiness
READY — actor, action and outcome were all recoverable from the input. The file
format is unresolved, so the story deliberately says "spreadsheet" rather than
choosing on the author's behalf.
