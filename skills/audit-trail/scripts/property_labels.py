"""Czech labels for document fields (keys in `DocumentEvent.info`) in the PDF report.

`info` is a JSON string whose keys are Document schema field names (`variableSymbol`, `issueDate`,
`partnerName`, ...), not the Czech labels the UI shows. The Events panel ("Události") translates them on
the client; this module does the same.

- `VERIFIED_LABELS`: label confirmed against the Events panel.
- `INFERRED_LABELS`: key from the Document schema, label not confirmed against the UI.

A field in neither set is shown under its raw key; no label is invented.
"""

from __future__ import annotations

VERIFIED_LABELS: dict[str, str] = {
    "type": "Typ dokumentu",
    "number": "Číslo",
    "variableSymbol": "Variabilní symbol",
    "issueDate": "Datum vystavení",
    "dueDate": "Datum splatnosti",
    "vatDate": "Datum UZP",
    "acceptDate": "Datum přijetí",
    "caseDate": "Datum případu",
    "totalAmount": "Celková částka",
    "currency": "Měna",
    "partnerIC": "IČ dodavatele",
    "partnerVAT": "DIČ dodavatele",
    "partnerName": "Jméno dodavatele",
    "partnerAddress": "Adresa dodavatele",
    "accountNo": "Číslo účtu",
    "bankCode": "Kód banky",
    "iban": "IBAN",
    "meIC": "IČ odběratele",
    "serie": "Dokladová řada",
    "description": "Popis",
    "invoiceType": "Typ faktury",
    "internalCode": "Interní číslo",
    "constantSymbol": "Konstantní symbol",
    "specificSymbol": "Specifický symbol",
    "advanceAmount": "Uhrazeno zálohou",
    "roundingAmount": "Částka zaokrouhlení",
    "bic": "BIC",
    "partnerStreetAndNumber": "Ulice a číslo popisné / orientační dodavatele",
    "partnerPostalCode": "PSČ dodavatele",
    "partnerCity": "Obec dodavatele",
    "partnerCountryCode": "Země dodavatele",
    "partnerAddressSupplement": "Doplňující informace k adrese dodavatele",
    "partnerEmail": "E-mail",
    "meVAT": "DIČ odběratele",
    "orderNo": "Číslo objednávky",
    "doNotPay": "Neproplácet",
    "accountingRule": "Předpis zaúčtování",
    "activity": "Činnost",
    "costCenter": "Středisko",
    "contract": "Zakázka",
    "paymentMethod": "Způsob platby",
    "vatReturnLine": "Řádek přiznání k DPH",
    "vatMode": "Režim DPH",
    "vatSupplyModeCode": "Kód režimu plnění",
    "vatApplyReductionCoefficient": "Použít koeficient pro krácení DPH",
    "vatFixedAssets": "Majetek (DPH řádek 47)",
    "exchangeRate": "Směnný kurz",
    "exchangeRateUnits": "Kurzové jednotky",
    "tag": "Externí označení",
}

INFERRED_LABELS: dict[str, str] = {
    "vatDocumentCode": "Kód dokladu DPH",
    "validFrom": "Platnost od",
    "validTo": "Platnost do",
    "effectiveFrom": "Účinnost od",
    "effectiveTo": "Účinnost do",
    "signatureDate": "Datum podpisu",
    "reviewDate": "Datum kontroly",
    "accountTerm": "Účetní období",
    "vatTerm": "Období DPH",
    "taxExclusiveAmount": "Částka bez DPH",
    "totalAmountFC": "Celková částka v cizí měně",
    "partnerLocalVAT": "Lokální DIČ dodavatele",
    "internalNumber": "Interní číslo",
}

# List fields (vats, lines, ...): the UI shows only the item count, not the content.
ARRAY_COUNT_LABELS_VERIFIED: dict[str, str] = {
    "vats": "Počet sazeb DPH",
    "lines": "Počet položek",
}
ARRAY_COUNT_LABELS_INFERRED: dict[str, str] = {}

# Only value 0 is known.
INVOICE_TYPE_LABELS_VERIFIED: dict[int, str] = {
    0: "Daňový doklad",
}

# Never shown as a "label: value" line: `status` is an internal code the UI does not show;
# `message` and `name` are rendered by their event type.
SUPPRESSED_KEYS = {"status", "message", "name"}


def label_for_property(key: str) -> tuple[str, bool]:
    """Return (Czech label, is_verified); an unknown field returns its raw key, unverified."""
    if key in VERIFIED_LABELS:
        return VERIFIED_LABELS[key], True
    if key in INFERRED_LABELS:
        return INFERRED_LABELS[key], False
    return key, False


def label_for_array(key: str) -> tuple[str, bool]:
    if key in ARRAY_COUNT_LABELS_VERIFIED:
        return ARRAY_COUNT_LABELS_VERIFIED[key], True
    if key in ARRAY_COUNT_LABELS_INFERRED:
        return ARRAY_COUNT_LABELS_INFERRED[key], False
    return f"Počet položek pole „{key}“", False


def label_for_invoice_type(value: int | str) -> tuple[str, bool]:
    try:
        value = int(value)
    except (TypeError, ValueError):
        return str(value), False
    if value in INVOICE_TYPE_LABELS_VERIFIED:
        return INVOICE_TYPE_LABELS_VERIFIED[value], True
    return str(value), False
