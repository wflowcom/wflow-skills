---
name: issued-invoices-import
description: "Import issued (outgoing) invoices that were created in another system – invoicing tool, e-shop, ERP, a hand-kept Excel – from any xls / xlsx / csv into wflow.com through the wflow MCP, optionally with their PDFs. Learns the file's layout once with the client, saves it as a mapping profile in the organization's wflow storage and reuses it on every later import. Handles invoices, credit notes, proforma / advance invoices and foreign currency, skips duplicates and asks what to do with customers missing from the partner register. Use whenever the user wants to get outgoing invoices from a spreadsheet into wflow, even without saying 'skill'. Trigger phrases: 'import issued invoices', 'import issued invoices from Excel', 'upload invoices from xls to wflow', 'export from invoicing into wflow', 'get issued invoices into wflow', 'import outgoing invoices'. Do not use for received invoices, orders, or for creating new invoices that do not exist yet anywhere."
---

# Import of issued invoices into wflow

Everything runs as the logged-in MCP user.

**Language:** talk to the user in their language (usually Czech or Slovak). Keep answers short.

## Prerequisites

- wflow MCP connected.
- A shell – to read the spreadsheet, run the scripts, upload PDFs and read the profile from wflow storage.
  Without one, say so and stop.
- Python 3 with `pandas` and `openpyxl`; `xlrd` as well for `.xls` files.
- `curl` – for the upload `command` from `create_file_upload_url` and the profile download.

## How to ask

- **Choices, not free text.** Every question with a fixed set of answers goes through the multiple-choice
  question tool (`AskUserQuestion` in Cowork and Claude Code), recommended option first. Free text only for
  open answers (a file path, a new value). The steps below say *what* to ask – word it yourself, short.
- **One thing per question.** Never merge two decisions into one question (e.g. "are the findings fine?" and
  "how do we fix them?").
- **Every question stands on its own.** The user may see only the dialog, not the text above it. Put into the
  question itself what you found, on which invoice (number, customer, amount, date), why it matters and what
  you propose. Two or three lines – not the whole source table. Offer "show the source rows" as an option when
  the context may not be enough.
- **Tables are confirmed in text, not in the dialog.** When the thing to confirm is a table (column mapping,
  invoice kinds, registers, preview), print it as a normal markdown table in the chat and end the message with
  one short question in text, e.g. "Is this right? Or tell me what to change." – no multiple-choice tool, so
  nothing covers the table. Never squeeze a table into the text of a dialog question.
- **The recommended option follows from the data only.** Never put your guesses into it ("these are test
  data", "the date is intentional"). If you do not know, recommend nothing.
- **Never ask about something you have not shown**, and never decide for the user what a question should
  decide (e.g. "the invoices will be created without PDFs" – ask instead).

## Where you run

- **Claude Code** runs on the user's computer: file paths are local, scripts read them directly.
- **Cowork** runs in a cloud container: the attached spreadsheet is in the container, but a folder on the
  user's computer (PDFs) is reached only through the device tools. Read
  `issued-invoices-import/references/environment.md` before touching PDFs – folder access and pairing PDFs
  from a list of names.

Run the scripts with plain `python` / `python3` – `-I` is fine too, the scripts find their own folder. If they
are not on disk, download all five with `get_playbook(name="issued-invoices-import", file="scripts/<name>")`
into one folder – `build_documents.py` and `apply_fixes.py` import `inspect_xls.py` from their own folder.

## Two paths

A saved profile decides which path you take (step 2). Do not ask what the profile already answers – say what
it says.

| # | First import – no profile | Repeat import – profile found |
| --- | --- | --- |
| 1 | Organization, file, PDFs yes / no | same |
| 2 | Structure, column mapping, invoice kinds, registers, missing fields, document type (2B) | Only the differences between profile and file, in one question (2A) |
| 3 | **Review of the file** (step 5) | same |
| 4 | Each issue (step 6) | same |
| 5 | PDFs – none / only some paired (step 7) | same |
| 6 | Customers missing from the register (step 7) | same |
| 7 | Preview (+ save profile) (step 8) | Preview (+ save profile changes) |
| 8 | Pilot (step 9) | same |

## Flow

### 1. Organization and file

- Find the organization via `list_organizations` (search by what the user says). Show the match and confirm
  it, as a choice when there is more than one.
- Get the spreadsheet and ask whether they have PDFs of the invoices (a folder) – optional.
- Run `issued-invoices-import/scripts/inspect_xls.py <file>` to see sheets, the header row and sample values.

### 2. Mapping profile

Look for a saved profile in wflow storage – where and how in
`issued-invoices-import/references/mapping-profile.md`.

**2A. Profile found – repeat import.** Say in one line which profile you use and from when (`updated`).
Compare its columns with the file's header. All present and nothing new → go on without a question.
Differences → one question listing each difference and the proposed change (renamed column, new column worth
mapping, missing column), options: apply all (recommended) / let me choose / stop. Keep the change in memory;
it is saved with the preview confirmation (step 8). Then go to step 3 – none of 2B is asked again.

**2B. No profile – first import.** Build it with the user, one question at a time:

1. **Structure** – one row = one invoice (VAT recap in columns), or one row = one line item (header repeats,
   rows grouped by invoice number). Say which and why; confirm.
2. **Column mapping** as a table *xls column → wflow field → sample value*. Mark unmapped columns. Confirm it
   in text below the table (see *How to ask*); a single column you could not decide may follow as its own
   dialog question.
3. **Formats** – date and number format, VAT rates, foreign currency, PDF pairing key (default: invoice number
   in the file name).
4. **Invoice kinds – always ask**, even without a kind column; one file often mixes invoices, credit notes and
   proformas. Run `issued-invoices-import/scripts/build_documents.py` with the draft profile (only for the proposal):
   - kind column → its distinct values with the proposed wflow kind (`kindMap`);
   - no kind column → `summary.kindProposal` as a table *prefix – count – examples – what the data shows
     (negative amounts, no VAT, words like "záloha" (advance) / "dobropis" (credit note)) – proposed kind*.
     Flag groups marked `mixed`. Store as `kindByPrefix` and/or `negativeTotalIsCreditNote`.

   Confirm the table in text.
5. **Registers the organization uses** – for cost centers, projects, contracts, activities, accounting rules,
   VAT return lines, VAT control statement lines and business cases call `list_register_*` with
   `pageSize: 1`; `totalItems > 0` = in use. Only whether the register is used, never its records. Table
   *register – used in wflow – in the xls* (just shown, no question about the table itself). For each used
   register missing in the xls ask in a dialog: fine without it / one fixed value for all
   (`accountingDefaults`). Store as `registersConfirmed`.
6. **Fields the file may not have** – one question each, only when missing:
   - **Case date** – recommended: from the VAT date; or issue date / none (`caseDateFrom`).
   - **Document series** – no recommendation; the series from `list_register_series` (read every page up to
     `totalItems`), "no series", "create a new one" (`patch_register_series` – send the whole record, check
     the schema first; preview + confirmation). Store as `serie`.
   - **Customer e-mail** – useful for sending invoices from wflow, optional: map a column / from the partner
     register / not wanted (`partnerEmail: "none"`, not asked again).
   - **Document lines** – header-only file: one line per VAT rate, optional (`linesPerVatRate`).
7. **Document type** – take the types from `get_me` (`documentTypes`, each with its `kind`) with kind
   `OutgoingInvoice`; only when `hasFullAccess` is false use `list_document_types` with
   `query: kind = "OutgoingInvoice"`. One → use it and say so, more → choose.

The profile is saved with the preview confirmation (step 8).

### 3. Build

Run `issued-invoices-import/scripts/build_documents.py <file> <profile.json> <out.json>` with the final
profile (a run in 2B was only a draft). It returns per invoice `issues` (need a decision) and `notes` (what it
filled in), plus `fileIssues` (duplicates or same variable symbol inside the file, a totals row it left out).
Do not show issues yet.

### 4. Duplicates in wflow – before anything else

For each invoice `list_documents` with `query: number = "<number>" and partnerIC = "<ic>"` (without a company
ID: number + `partnerName`). Start `fixes.json` with `sheet`, `headerRow` and `decimalComma` copied from the
profile's `source`. Every invoice already in wflow goes to it as
`{"row": <row>, "reason": "<already in wflow>"}` in `skipRows`; re-run `build_documents.py` with
`--fixes fixes.json`. Tell the user in one line, e.g. "FV2026-0103 is already in wflow (imported on
2026-10-07), skipping it." No question – an existing document is never overwritten. This must happen before
the review, otherwise a duplicate shows up as an "error" to fix.

### 5. Review of the file – always ask

Ask whether to review the file – options: review it (recommended) / skip. Never skip the question and never
turn the review into tips at the end.

On a yes run `issued-invoices-import/scripts/review_xls.py <out.json>`. It checks gaps in the invoice number
series, invoices outside the file's main period, dates in the future, issue date more than 15 days after the
VAT date, the company ID (IČ) checksum, the VAT ID (DIČ) format (CZ + 8 digits must equal CZ + company ID;
CZ + 9–10 digits is a birth number of a natural person / sole trader – only its format is checked), VAT =
base × rate per rate, zero amounts, a foreign customer with Czech VAT, one customer with several names or
company IDs, and a totals row that does not match the sum.

- `file` findings: one question per finding, each self-contained, e.g. "The totals row in the file says
  58,005 CZK, the invoices add up to 49,535 CZK (difference 8,470 CZK). The export may be incomplete." –
  options: it is fine, go on / the export is incomplete, I will send a new one / show source rows.
- `invoices` findings join the invoices' issues in step 6.

### 6. Issues

If there are none, say so in one line and go on. Otherwise first one short line – "X invoices have findings"
– and ask how to deal with them: fix them one by one with me (recommended) / import only the invoices without
issues / I will fix the file myself.

**One by one** – right after that choice, without any free-text question in between, start with the first
issue: one question per issue, self-contained (invoice number, customer, amount, date, what is wrong, your
proposal), with concrete options, e.g.:

- invoice outside the series / period → leave it out / import it anyway / change the number;
- VAT does not add up → correct the total to base + VAT (show the number) / correct the VAT / leave it out;
- unknown kind → the wflow kinds as options;
- invalid date → the proposed date / leave it out.

Add "show the source row" when it helps. Record each answer in `fixes.json` (a cell change or a skipped row
with its reason; reasons end up as cell comments in the client's file, so write them in the client's
language). Then run `issued-invoices-import/scripts/apply_fixes.py <file> <fixes.json> <out>` – a
**corrected copy** (`<name>_opraveno.xlsx`, changes yellow with the original value in a comment, left-out
rows grey) – and `build_documents.py` on it with `--fixes fixes.json`. It must come back without issues.
Offer the corrected file to the client at the end.

**I will fix the file myself** → wait for the new file and start again at step 3.

### 7. PDFs, register codes, customers

- **PDFs** (if the user has them) – pair them with `issued-invoices-import/scripts/pair_pdfs.py` (in Cowork
  from a list of names, see `issued-invoices-import/references/environment.md`). Do not bury the result in
  the preview:
  - **none paired** → ⚠️ question: no PDF matches any invoice number (show a few PDF names and a few invoice
    numbers) – options: a different folder / a different pairing key / go on without PDFs.
  - **only some paired** (`partial`) → ⚠️ question with the counts (X of Y) and the invoices without a PDF –
    options: fine, import them without a PDF / some are missing, I will add them / import only invoices with
    a PDF.
  - Mention PDFs that belong to no invoice and names that matched more than one.
- **Register codes** in the mapping (cost center, project…) – check each distinct value against its register.
  Unknown → one question: add it to the register / map to an existing one / import without it.
- **Customers** – look each company ID up in `list_register_partners` (`query: ic = "<ic>"`). Found → link it
  with `partner: {id}` – without it wflow only copies the name, company ID and address onto the document and
  leaves `partner` empty. No e-mail on the invoice and the profile does not say `"none"` → take the partner's
  `mailAddress`. Missing → **ask every time** (never store the answer): create in the register and link /
  only the data from the file. A new customer goes through `patch_register_partners` with name, `ic`, `vat`,
  `mainAddress`, `customer: true`, `isValid: true` – each sent record replaces the stored one as a whole. It
  returns `id: null`: find the new partner with `list_register_partners` by its company ID (it comes back with
  `supplier: true` as well).

### 8. Preview and one confirmation

One table: what will be created (count by kind, total by currency), skipped as duplicates, left out,
customers to create, register codes to add, PDFs, profile changes to save. Then ask in text below the table,
e.g. "Should I create one pilot invoice first? Or tell me what to change." The confirmation covers saving the
profile (new or changed) to wflow storage. Write only after an explicit yes.

### 9. Pilot, then the rest

Create the **first invoice only** (and the profile, customers, codes it needs), read it back with
`get_document` and show the key fields next to the source row, then ask – options: it is right, create the
rest / something is wrong.

For each invoice: `update_document` without `id` creates the document from data, no file needed – also for a
document type with `docCreatingMethod = Upload`. The returned id is the only sign it was created: keep
*source row → document id* as you go, so a failure in the middle can be resumed without duplicates. Then the
PDF if there is one: `create_file_upload_url` → run its `command` with the file path (in Cowork see
`issued-invoices-import/references/environment.md`) → `upload_document_file` with `main: true`. Each
`uploadId` works once.

### 10. Summary

Short table: created / skipped as duplicates / left out / customers created / PDFs attached / errors. The
documents are in `SentToReview` – wflow moves them there on its own; the flow status cannot be set. If
invoices were left out, say they can be imported later on their own.

## Common rules

1. **Preview and one confirmation before any write** – profile, customers, documents.
2. **Never `update_register_partners`** – it retires every partner you do not send. Only
   `patch_register_partners`.
3. **Do not set `setAsFilled`** – it changes only an internal status, nothing in the app.
4. **Do not overwrite existing documents.** Duplicates are skipped, never updated. Never call
   `delete_document` – it deletes for good; test documents are deleted by the user in the app.
5. **Rate limit** ~200 requests/min, `429` above it, the MCP does not retry. On `429` wait ~60 s and continue
   from the *source row → document id* record.
6. **No IDs in chat** unless asked.
7. **Do not stop at the skill's border** – a missing register value can be added through the MCP right away,
   with preview and confirmation.
8. **Read back every write** – a new series or register code with its `list_register_*`, a new partner by
   its company ID, the profile folder and file as in `issued-invoices-import/references/mapping-profile.md`, a
   document by its returned id (the pilot also with `get_document`).

## References

- `issued-invoices-import/references/environment.md` – Cowork vs. Claude Code: PDF folder, pairing from names.
- `issued-invoices-import/references/mapping-profile.md` – profile format, where it lives in wflow storage,
  how to read and write it.
- `issued-invoices-import/references/field-mapping.md` – wflow fields, typical Czech column names, VAT, kinds,
  currency.
- `issued-invoices-import/scripts/inspect_xls.py` (layout), `build_documents.py` (payloads, issues, kind
  proposal), `review_xls.py` (review), `apply_fixes.py` (corrected copy), `pair_pdfs.py` (PDFs).
