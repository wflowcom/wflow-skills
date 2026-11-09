# Assignment conditions

The conditions available when assigning an approval path in a workflow automation (complete list from the wflow
UI). The Czech UI label is in brackets – use it with Czech-speaking clients, it is what they see in wflow.

| Group | Conditions | Question for the client |
| --- | --- | --- |
| What document | Document kind (Druh dokumentu), Document type (Typ dokumentu), Invoice type (Typ faktury), Document series (Dokladová řada), Data source (Zdroj dat), Description (Popis) | Does approval differ by document kind, series, or where the document came from? |
| From whom | Partner (Partner), Partner company ID (IČ partnera), Partner VAT ID (DIČ partnera), Partner local VAT ID (Místní DIČ partnera) | Do some suppliers have their own approval or an exception? |
| How much | Total amount (Celková částka), Total amount without VAT (Celková částka bez DPH), Currency (Měna), Payment method (Způsob platby) | What are the amount limits – with or without VAT? |
| What for (accounting) | Cost center (Středisko), Contract (Zakázka), Activity (Činnost), Accounting rule (Předpis zaúčtování), Budget (Budget) | Is the head of the cost center / contract / budget responsible? |
| Who created / sent it | Created by user (Vytvořil uživatel), Sender e-mail (Email odesílatele), Employee (Zaměstnanec), Card (Karta) | Does the approver depend on who created the document? Receipts, cards? |
| Links and state | Number of links (Počet propojení), Matched transactions (Spárované transakce), Tag (Štítek), Validation warnings (Validační varování), Validation errors (Validační chyby) | Should documents with a matched order or with an error take another path? |

## Operators by field type

| Type | Fields | Operators |
| --- | --- | --- |
| Register / selection | all fields not listed below | equals (se rovná), does not equal (se nerovná), is in list (je v seznamu), is not in list (není v seznamu), is empty (je nevyplněné), is filled (je vyplněné) |
| Number | Total amount, Total amount without VAT, Number of links | equals (se rovná), does not equal (se nerovná), greater than or equal (se rovná nebo je větší než), greater than (je větší než), less than or equal (se rovná nebo je menší než), less than (je menší než), between (je v rozmezí) |
| Free text | Description | the register operators + contains (obsahuje) |
| Validation | Validation warnings, Validation errors | contains (obsahuje), does not contain (neobsahuje) |

## Combining conditions

- Conditions inside one condition set apply together (AND).
- Condition sets can be combined with OR, **also across different condition types** (e.g. Partner company ID OR
  Partner VAT ID).

## Ideas worth offering

- **Validation errors** – documents with an error go to a separate path (e.g. accountant to fix).
- **Number of links** – an invoice matched to an approved order can get a shorter path.
- **Data source** – distinguishes e-mail, ISDOC, ERP, mobile.
- **Budget is empty** – documents without a budget go to the person handling exceptions.
