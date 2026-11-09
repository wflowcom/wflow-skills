# Mapping profile

The profile records how one client's spreadsheet maps to wflow, so the next import needs no questions. It
lives in the organization's wflow storage, never in the assistant's memory.

## Where

- Folder **`AI importy`** in the storage root. Find it with `list_storage_folder_children` (no `folderId` =
  root).
- File **`profil-import-vydanych-faktur.json`**. One organization usually has one source system; if the
  client imports from two different systems, use a suffix (`profil-import-vydanych-faktur-eshop.json`) and
  ask which one to use.

## Read

1. `list_storage_files` with `query: folderId = "<folder id>"`; read every page up to `totalItems` and find
   the profile files by name.
2. `download_storage_file` → `downloadUrl` + `zipPassword`. The link serves a password-protected AES zip, not
   the file. Download it (`curl -o profile.zip "<downloadUrl>"`) and open it with
   `7z x -p'<zipPassword>' profile.zip` or `bsdtar --passphrase` where available; otherwise (Cowork has no
   `7z`) with the script from `get_download_archive_format`. `unzip` and Python's `zipfile` cannot open it.
   Never show the password or the link in chat.

## Write

Save a new or changed profile **with the preview confirmation** (SKILL.md step 8) – not as a separate
question before or after the import.

1. Save the JSON locally (UTF-8).
2. Folder missing → create it with `update_storage_folder` (`folder: {name: "AI importy"}`, no `id`, no
   `parentId`).
3. `create_file_upload_url` → run the returned `command` with the local file path.
4. `upload_storage_file` with `folderId`, `filename`, `uploadId`. The same name without
   `overrideIfExists: true` creates a numbered copy – use it when replacing an existing profile (say that the
   old one is overwritten).
5. A new folder or file gets Everyone rights (a file does not inherit the folder's): set empty rights with
   `set_storage_folder_rights` / `set_storage_file_rights` (`teams: []` – only full-access users see it).
6. Verify: the folder with `list_storage_folder_children`, the file with `list_storage_files`, the rights with
   `get_storage_folder_rights` / `get_storage_file_rights`.

## Format

```json
{
  "version": 1,
  "name": "Export from invoicing tool XY",
  "updated": "2026-10-27",
  "documentType": {"id": "<id>", "name": "Issued invoices"},
  "source": {
    "sheet": "Invoices",
    "headerRow": 1,
    "structure": "header",
    "dateFormats": ["%d.%m.%Y", "%Y-%m-%d"],
    "decimalComma": true
  },
  "columns": {
    "number": "Číslo faktury",
    "variableSymbol": "VS",
    "issueDate": "Vystaveno",
    "vatDate": "DUZP",
    "dueDate": "Splatnost",
    "partnerName": "Odběratel",
    "partnerIC": "IČ",
    "partnerVAT": "DIČ",
    "partnerStreet": "Ulice",
    "partnerCity": "Město",
    "partnerPostalCode": "PSČ",
    "partnerCountry": "Stát",
    "partnerEmail": null,
    "currency": "Měna",
    "exchangeRate": "Kurz",
    "taxExclusiveAmount": "Základ celkem",
    "taxAmount": "DPH celkem",
    "totalAmount": "Celkem",
    "description": "Text",
    "orderNo": "Objednávka",
    "kind": "Typ dokladu",
    "caseDate": null,
    "serie": null
  },
  "caseDateFrom": "vatDate",
  "serie": {"code": "VF"},
  "partnerEmail": "none",
  "linesPerVatRate": false,
  "kindByPrefix": {"FV": "TaxInvoice", "DB": "CreditNote", "ZF": "Proforma"},
  "accountingDefaults": {"accountingRule": "PZ01"},
  "registersConfirmed": {"used": ["costCenters", "accountingRules"], "inFile": ["costCenters"], "date": "2026-10-29"},
  "vatColumns": [
    {"rate": 21, "base": "Základ 21 %", "tax": "DPH 21 %"},
    {"rate": 12, "base": "Základ 12 %", "tax": "DPH 12 %"},
    {"rate": 0, "base": "Osvobozeno", "tax": null}
  ],
  "lineColumns": null,
  "accountingColumns": {"costCenter": "Středisko", "project": null, "contract": null, "activity": null},
  "kindMap": {"Faktura": "TaxInvoice", "Dobropis": "CreditNote", "Zálohová faktura": "Proforma"},
  "negativeTotalIsCreditNote": true,
  "defaults": {"currency": "CZK", "countryCode": "CZ"},
  "variableSymbolFromNumber": true,
  "pdf": {"key": "number", "note": "PDF named <invoice number>.pdf, also matches <number>_anything.pdf"}
}
```

- `columns` values are header texts of the spreadsheet (here a Czech one), `null` = not in the file.
- `structure: "lines"` → fill `lineColumns` instead of relying on `vatColumns`:
  `{"description", "quantity", "unit", "unitPrice", "vatRate", "lineBase", "lineTax", "lineTotal",
  "amountsIncludeVat": false}`. Rows are grouped by `number` (+ `partnerIC`).
- Without `vatColumns` and without lines, one VAT row is built from `taxExclusiveAmount`, `taxAmount` and a
  `vatRate` column (`columns.vatRate`).
- `kindMap` keys are compared case-insensitively and trimmed; unknown value → issue, not a guess.
- `caseDateFrom` – used only when `columns.caseDate` is `null`: `"vatDate"` (default proposal), `"issueDate"`
  or `null` (no case date). A proforma without a VAT date falls back to the issue date.
- `serie` – fixed document series for every invoice when the file has no series column (`columns.serie`);
  `null` = the user chose none. A series column wins over the fixed value.
- `partnerEmail` – `"none"` = the client does not want e-mails, do not ask again; omitted = take the
  partner's `mailAddress` from the register. A `columns.partnerEmail` column always wins.
- `linesPerVatRate` – header-only files: `true` creates one document line per VAT rate.
- `kindByPrefix` – kind by the letters before the first digit of the invoice number, used when the file has
  no kind column. Order: kind column → `kindByPrefix` (longest prefix) → `negativeTotalIsCreditNote` →
  `TaxInvoice`.
- `accountingDefaults` – one fixed register code for every invoice (keys as in `accountingColumns`:
  costCenter, project, contract, activity, accountingRule, vatReturnLine, vatControlStatementLine,
  businessCase); a column value wins.
- `registersConfirmed` – which registers were in use in wflow and which the file has, as confirmed by the
  user. Ask again only when the set of used registers differs.
- Never store the answer to "create missing customers?" in the profile – it is asked every import.
