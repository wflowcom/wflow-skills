---
name: missing-recurring-invoices
description: "For accountants: find regular received invoices (rent, energy, licences, services) missing in wflow.com for a month and prepare an Excel basis for accruals with amount, cost centre, contract, activity and account through the wflow MCP; also releases last month's accruals. Compares the client's Excel list of regular payments with received invoices, or proposes the list from history. Use whenever the user asks which recurring invoices are missing or have not arrived, wants an accruals basis, accruals or their release, or mentions regular payments, in any language and even without the word 'skill'. Read only. Not for VAT periods or importing invoices."
---

# Missing recurring invoices (basis for accruals)

## Prerequisites

- wflow MCP connected.
- A shell with Python 3 and `openpyxl` (no pandas) for `missing-recurring-invoices/scripts/recurring_check.py`
  and `missing-recurring-invoices/scripts/inspect_xls.py`. Without a shell say so and stop. Run them with
  plain `python` / `python3`; save what you read from the MCP as JSON files in a working folder and pass the
  paths.
- If the scripts are not on disk, download both (`recurring_check.py`, `inspect_xls.py`) with
  `get_playbook(name="missing-recurring-invoices", file="scripts/<name>")` into one folder.
- Claude Code: paths are local; the Excel list is read directly.
- Cowork: runs in a cloud container. Read `missing-recurring-invoices/references/environment.md` before
  reading a file from the user's computer or handing over the output Excel.

**Language:** talk to the user in their language (usually Czech or Slovak). Keep answers short. The Excel
outputs are in Czech (the script writes them); quote their sheet names and review kinds as they are.

## Guiding the user (always)

- **Never end with just a file.** After every output say in two or three lines what it means, then offer the
  next step as a multiple-choice question (see "Next step" in each mode).
- **Never hand over an output you know is wrong** and never ask the user to fix the Excel. If the script flags
  something you can resolve from the data you already have (e.g. a supplier with two kinds of invoices),
  resolve it first; if you cannot, say exactly what is unclear and ask.
- Before the first call say in one sentence what will happen (e.g. "I'll read the received invoices for …,
  compare them with the list and prepare the accruals Excel.").

## How to ask

- **Choices, not free text.** Questions with a fixed set of answers go through the multiple-choice question
  tool (`AskUserQuestion` in Cowork and Claude Code), recommended option first. Free text only for open
  answers (a month, a file). Word the questions yourself, short.
- **One thing per question.** Never merge two decisions into one question. Several independent questions in
  one dialog are fine (e.g. organization, mode, month, date at the start).
- **Every dialog question stands on its own** – what you found, for which supplier / row, what you propose.
  Two or three lines.
- **Tables go into the chat, never into a dialog question.** Column mapping and previews are a markdown table
  in the chat. The table is then confirmed by a dialog question **on its own** ("Does the column mapping in the
  table above fit?" – Yes / I want to change something). Never ask anything else in the same turn – an
  unanswered text question is not a confirmation.
- **The recommended option follows from the data only**, never from guesses.
- **Never edit the script's JSON outputs by hand.** A user's decision goes back through the script's options
  (e.g. `--confirm`) and the script is run again.

## Start

1. **Organization** – `list_organizations`, confirm when more than one matches.
2. **Mode** – ask, unless the user's words say it:
   1. **Check a month** – the client has a list of regular payments (Excel). Recommended when a file is
      attached or a profile exists.
   2. **Propose the list from history** – no list yet; the skill proposes one from the last 6 months.
3. **Month** – `YYYY-MM`; "last month" = the month before today. For Mode 2 the month is the last month of the
   history window (default: last full month).
4. **Deciding date** – ask: **tax point date** (DUZP, `vatDate`; recommended – the period the service belongs
   to, same as the accrual; without it the issue date is used) / **acceptance date** (`acceptDate`, when the
   invoice arrived). With a saved profile recommend the date it remembers (`dateField`).
5. **Mode 1 only – release last month** – ask whether the user has the accruals Excel for <previous month> to
   release at the same time (yes, I'll attach it – recommended when the user mentions release / last month /
   no). The file is the Excel this skill made last month (sheet "Podklad pro dohady"), possibly edited by the
   accountant – what they actually booked counts.

## Read the invoices (both modes)

`list_documents`, all pages (`pageSize: 100`, compare with `totalItems`). Date filters take a plain date on
the date-time fields (`vatDate >= "2026-07-01"`):
- `type.kind = "IncomingInvoice" and vatDate >= "<start>" and vatDate < "<end>"` (or `acceptDate`),
- with the tax point date also `type.kind = "IncomingInvoice" and vatDate = null and issueDate >= "<start>"
  and issueDate < "<end>"`,
- invoices without the deciding date at all (they would make a regular invoice look missing):
  `type.kind = "IncomingInvoice" and vatDate = null and issueDate = null and created >= "<start>"`
  (with the acceptance date: `acceptDate = null and created >= "<start>"`).

Window: Mode 1 = checked month + 3 months before (12 when the list has a yearly row without months); when
releasing, the previous month is already inside. Mode 2 = 6 months. Pass the window start to `match`
(`--window-start`).

**Save every response unchanged as a file and merge them with the script** – never retype or reshape
documents yourself:
- A response the tool already saved to a file (too large for the chat) → use that file path.
- A small response → write its text into a file unchanged (e.g. `cat > resp3.json <<'EOF'` … `EOF`).
- `python missing-recurring-invoices/scripts/recurring_check.py collect resp1.json resp2.json resp3.json --out docs.json`
  keeps only the needed fields, merges pages and prints `complete` – when it is `false`, read the missing
  pages first.

Credit and debit notes, proformas, tax documents for a payment and invoices rejected in approval never count
as an arrived invoice and are not used for averages – the script handles it, the summary only counts them. Do
not list them in chat.

## Mode 1 – check a month

### 1. The list of regular payments

1. Look for the profile: folder `AI importy` in the storage root → file `profil-pravidelne-faktury.json`
   (how to read it: `missing-recurring-invoices/references/mapping-profile.md`). Found → say so in one
   line and use it; ask for the Excel file only.
2. A list made by Mode 2 (template columns) needs no mapping – use profile `template`.
3. No profile: `python missing-recurring-invoices/scripts/inspect_xls.py <file>` → propose the mapping
   from headers and samples. Show a table *meaning → column → sample* for: company / person (`name`), company
   ID – IČ (`ic`), description (`description`), keyword (`keyword`), amount (`amount`), tolerance
   (`tolerance`), frequency (`frequency`), billing months (`months`), cost centre – Středisko (`costCenter`),
   contract – Zakázka (`contract`), project – Projekt (`project`), activity – Činnost (`activity`), analytical
   account – Analytický účet (`account`). Only name **or** IČ is required; mark the rest "not in the file".
   Under the table **only** the dialog question "Does the column mapping in the table above fit?" (Yes / I want
   to change something) – nothing else in that turn. "I want to change something" → ask what, show the
   corrected table, ask again. **Only after "Yes"** ask the next dialog question: is the amount **excl. VAT**
   (recommended for accruals) or **incl. VAT**? Save as `profile.json`. Without an explicit "Yes" never go on
   and never save the profile to wflow.
4. `python missing-recurring-invoices/scripts/recurring_check.py normalize --xls <file> --profile profile.json|template --out list.json`
   The output lists `issues` (unknown months or frequency, an amount that is not a number, duplicate rows,
   several rows of one supplier that cannot be told apart, empty list). **Show every issue** with its row and
   ask once: continue (the skill uses the fallback named in the issue) / I'll fix the list first. An empty list
   stops the run.

### 2. Match

`python missing-recurring-invoices/scripts/recurring_check.py match --list list.json --docs docs.json --period YYYY-MM --date-field vatDate|acceptDate --window-start <start> --org <subdomain> --out result.json`

`warnings` in the result must be said to the user before anything else, in plain words: unfinished month,
incomplete paging, history shorter than needed, no invoices at all, amounts in the list probably with VAT.
With "no invoices at all" or incomplete paging stop and fix the reading first.

Rules the script applies (say them only if asked): supplier by IČ, without IČ by the normalized name; several
rows of one supplier are told apart by keyword and amount (tolerance default 20 %), a tie goes to review
("Ke kontrole"); quarterly / yearly rows count only in their months; an invoice counts as arrived in any
workflow status (those not in the ERP are flagged); an invoice cancelled by a credit note on the full amount
does not count.

**"Možná došla pod jiným IČ / názvem"** (maybe arrived under another IČ / name) – before the output ask about
each such item in a dialog question (row, invoice number, IČ / name in the list vs. on the invoice): **yes,
it is the same payment** / **no, an accrual is needed**. For every "yes" write `confirm.json`
(`[{"row": <list row>, "document": "<invoice number>"}]`) and run `match` again with `--confirm confirm.json`.
The invoice then counts as arrived with a note; say in the summary that the IČ / name on the invoice or in the
list should be corrected. Warnings about a confirmation that could not be used must be said.

### 3. Accounting codes from history

The `list_documents` summary has no cost centre, contract, project or activity – they come from
`get_document` (`accounting` header and `lines[]`). For missing rows the script names the last invoice in
`detailIds`. Call `get_document` for each (only these), save each response unchanged as a file and run
`python missing-recurring-invoices/scripts/recurring_check.py collect det1.json det2.json --kind details --out details.json`.
When that invoice is split across several cost centres / contracts / accounts and the list gives no codes, the
accrual is split by the same shares – one row per combination.

### 4. Release last month (when the Excel was attached)

1. For credit and debit notes of the previous month from suppliers of the attached accruals call
   `list_document_links` and save `{"<note id>": ["<linked id>", …]}` as `links.json` (skip when there are
   none). Users rarely link documents, so the script falls back to supplier + period.
2. `python missing-recurring-invoices/scripts/recurring_check.py release --accruals <last month xlsx> --list list.json --docs docs.json --period <previous YYYY-MM> --date-field … --links links.json --org … --out release.json`
3. Groups: **arrived – release** ("Došlo – rozpustit": invoice, difference to the accrual; credit / debit notes
   shown with the net amount), **still missing – accrual stays** ("Pořád chybí – dohad trvá"), **to check**
   ("Ke kontrole": several invoices, cancelled and replaced invoice, note that cannot be assigned). The release
   amount is the invoice; notes are information.

### 5. Output

`python missing-recurring-invoices/scripts/recurring_check.py report --result result.json --details details.json [--release release.json] --out Dohady_<org>_<YYYY-MM>.xlsx`

Sheets: Souhrn (summary, with warnings and list issues), Podklad pro dohady (accruals basis), Došlé (arrived),
Ke kontrole (to check), and Rozpuštění <previous month> (release) when releasing. The project column appears
only when some value is filled. In chat: a short table – missing (count + total), arrived (of which not in
ERP), to check, and for the release: to release / still missing. Then list the missing rows (company,
description, amount) and every "Ke kontrole" item in one line each. Do not advise on the booking itself –
that is the accountant's call.

### 6. Next step (always ask)

One multiple-choice question with what applies, recommended first:
- **Save the mapping to wflow** (only when the mapping is new or changed) – write the profile as in
  `missing-recurring-invoices/references/mapping-profile.md` ("Write"), with `dateField`.
- **Add the suppliers missing from the list** – only when "Ke kontrole" has items of the kind "Pravidelný
  dodavatel mimo seznam" (regular supplier not on the list), and only those suppliers (never one-off invoices
  from other review items, e.g. foreign currency without a rate): give the rows in the template columns ready
  to paste.
- **Done** – and say in one line: next month attach this Excel (edited to match the booking if needed) and the
  accruals for <month> will be released together with the new check.

## Mode 2 – propose the list from history

1. Read received invoices for the last **6 months** up to the chosen month (as above).
2. `python missing-recurring-invoices/scripts/recurring_check.py suggest --docs docs.json --end YYYY-MM --months 6 --date-field … --out Pravidelne_platby_<org>.xlsx`
   – suppliers with an invoice in ≥ 2/3 of the months that have data (monthly) or in a 3-month rhythm
   (quarterly). A supplier with two kinds of invoices (rent + energy) is already split into rows by the invoice
   description, each with its own keyword, amount and account. Amount = median of the last 3 invoices without
   VAT (in CZK; foreign currency converted by the invoice rate, with a note). An invoice cancelled by a credit
   note on the full amount is left out. One supplier under two IČ (typo) is merged into one row with a note.
3. Read the output before handing the Excel over:
   - `unclear` = a supplier with several invoices a month the script could not split. Look at those invoices
     (`docs.json`) yourself; if you can tell the payments apart, fix the rows in the Excel (keyword, amount,
     account); if not, ask the user one question about it.
   - `check` = an invoice more than 20 % off the usual amount, or one supplier under two IČ. Ask about each in a
     dialog question (e.g. "IT Servis: usually CZK 18,000, in October CZK 31,000 – which amount goes into the
     list?" – 18,000 (recommended) / 31,000) and fix the Excel by the answer.
   - `withoutDate` > 0 = invoices without the deciding date are not in the proposal – say so in one line
     (supplier, number).
   - `dataFrom` later than the window start → say that history in wflow starts only then.
4. Show the proposed rows as a table (company, keyword, amount, frequency, account).
5. **Next step (always ask):** "Check <month> with this list right away?" – **yes** (recommended: run Mode 1
   with this file and profile `template`, same organization, month and date, no mapping questions) / **I'll
   edit the list first** (say: fill cost centre / contract / activity where you want them fixed, then attach
   it again) / **done**.

## Common rules

1. **Read only** – never change, tag, lock or delete documents. The profile (and its folder) is the only
   write, after confirmation.
2. **Rate limit** ~200 requests/min; `429` → wait ~60 s and continue.
3. **No IDs in chat** unless asked.
4. The output holds client data – keep it in the working folder, do not publish it.

## Files

- `missing-recurring-invoices/references/mapping-profile.md` – profile location, reading, writing,
  format.
- `missing-recurring-invoices/references/environment.md` – Cowork: files on the user's computer, the output
  Excel.
- `missing-recurring-invoices/scripts/inspect_xls.py` – layout of the list.
- `missing-recurring-invoices/scripts/recurring_check.py` – `collect`, `normalize`, `match`, `release`,
  `report`, `suggest`, `selftest`.
