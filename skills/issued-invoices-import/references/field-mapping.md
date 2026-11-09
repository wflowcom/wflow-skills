# wflow fields for issued invoices

Payload of `update_document` (no `id` = create). Dates as `YYYY-MM-DDT00:00:00`.

| Profile key | wflow field | Typical column names (CZ/SK) | Note |
| --- | --- | --- | --- |
| number | `number` | Číslo faktury, Číslo dokladu, Doklad, Faktura č. | required |
| variableSymbol | `variableSymbol` | VS, Var. symbol | missing → digits of the number if `variableSymbolFromNumber` |
| issueDate | `issueDate` | Vystaveno, Datum vystavení, Dátum vyhotovenia | required |
| vatDate | `vatDate` | DUZP, Datum zdanitelného plnění, DUZP / DDP | missing → issueDate (say so); a proforma gets none |
| dueDate | `dueDate` | Splatnost, Datum splatnosti | |
| caseDate | `caseDate` | Datum případu, Datum účetního případu | missing → ask; proposal: from the VAT date (`caseDateFrom`) |
| serie | `serie.code` | Řada, Číselná řada, Dokladová řada | missing → ask, no proposal; `list_register_series`, create via `patch_register_series`; wflow resolves `serie: {code}` to the full series record |
| partnerName | `partnerName` | Odběratel, Zákazník, Firma, Název | required (or partnerIC) |
| partnerIC | `partnerIC` | IČ, IČO | company ID; key for duplicates and the register; stored as a number in Excel it loses leading zeros – the script pads it to 8 digits and reports it |
| partnerVAT | `partnerVAT` | DIČ, IČ DPH | VAT ID |
| partnerStreet/City/PostalCode/Country | `partnerMainAddress.streetAndNumber / city / postalCode / countryCode` | Ulice, Město / Obec, PSČ, Stát / Země | country as ISO-2 |
| partnerEmail | `partnerEmail` | E-mail | optional; missing → ask once (useful for e-mailing invoices from wflow), else the partner's `mailAddress` from the register |
| currency | `currency` | Měna | ISO-3, default from the profile |
| exchangeRate | `exchangeRate` | Kurz | foreign currency only |
| taxExclusiveAmount | `taxExclusiveAmount` | Základ, Bez DPH, Celkem bez DPH | |
| taxAmount | `taxAmount` | DPH | |
| totalAmount | `totalAmount` | Celkem, Celkem s DPH, K úhradě | required |
| description | `description` | Text, Popis, Předmět | |
| orderNo | `orderNo` | Objednávka, Č. objednávky | |
| kind | `invoiceType` | Typ, Druh dokladu | via `kindMap` |
| accountingColumns.costCenter / project / contract / activity | `accounting.costCenter.code` … | Středisko, Zakázka, Projekt, Činnost | value must exist in the register |

Fixed by the skill: `type: {id: <profile documentType.id>, kind: "OutgoingInvoice"}`.

## VAT

`vaTs: [{type, rate, base, tax}]`, `type` by rate (CZ since 2024):

| Rate | type |
| --- | --- |
| 21 | `Basic` |
| 12 | `FirstReduced` |
| 10, 15 (older / SK) | ask – `FirstReduced` or `SecondReduced` |
| 0 / exempt | `Exempt` |

SK rates (23 / 19 / 5 since 2025) are not in the default map – ask and store the map in the profile
(`vatTypes`). Check: sum of `base + tax` ≈ `totalAmount` (± 1 for rounding; rounding difference →
`roundingAmount`).

## Lines for header-only files

With `linesPerVatRate: true` the script adds one line per VAT rate: description `<invoice text> – 21 %` (or
`– osvobozeno` for exempt; without an invoice text `Plnění` – the line text is written to the client's
document in Czech), quantity 1, unit price = base, VAT rate and type, line `totalAmount` = base. A proforma
without VAT recap gets no lines.

A line's `totalAmount` is **without VAT** – wflow shows it as the line total excluding VAT. Sending base + VAT
shows a warning on the line.

## Document kinds (`invoiceType`)

| Kind | Value |
| --- | --- |
| Invoice | `TaxInvoice` (default) |
| Credit note | `CreditNote` |
| Debit note | `DebitNote` |
| Proforma / advance invoice | `Proforma` |

Which kind an invoice gets: the order under `kindByPrefix` in
`issued-invoices-import/references/mapping-profile.md`. Keep the amounts' sign as it is in the file.

## Foreign currency

`currency` (e.g. EUR) + `exchangeRate` (+ `exchangeRateUnits`, default 1). Amounts are taken as they are in
the file (in the invoice currency).
