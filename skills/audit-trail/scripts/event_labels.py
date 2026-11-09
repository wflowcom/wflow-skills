"""Czech labels for `DocumentEventType` values in the PDF report.

- `VERIFIED_LABELS`: label confirmed against the Events panel ("Události") in the wflow UI.
- `UNVERIFIED_LABELS`: label not confirmed against the UI.

`label_for` says whether a label is verified; unverified types that occur in the data go to the run summary.
"""

from __future__ import annotations

VERIFIED_LABELS: dict[str, str] = {
    "Create": "Vytvořeno",
    "Update": "Aktualizováno",
    "Locked": "Zamknuto",
    "Unlocked": "Odemknuto",
    "FileAdded": "Soubor přidán",
    "TaskAdded": "Úkol přidán",
    "TaskProcessed": "Úkol zpracován",
    "Approved": "Schváleno",
    "SetDocumentApprovals": "Nastavena schvalovací cesta",
    "ChangedFlowStatus": "Změněn stav zpracování",
    "Returned": "Vráceno",
    "ChangeDocumentApprovals": "Změněná schvalovací cesta",
    "SetMainFile": "Hlavní soubor změněn",
}

UNVERIFIED_LABELS: dict[str, str] = {
    "Delete": "Smazáno",
    "Restore": "Obnoveno",
    "Unapproved": "Zrušeno schválení",
    "Rejected": "Zamítnuto",
    "FileDeleted": "Soubor odstraněn",
    "SetDocumentRights": "Nastavena práva",
    "DeleteDocumentApprovals": "Odstraněna schvalovací cesta",
    "AddDocumentPayment": "Přidána platba",
    "UpdateDocumentPayment": "Aktualizována platba",
    "ChangeProperty": "Změněna vlastnost",
    "TimeStamped": "Časové razítko",
    "Signed": "Podepsáno",
    "AddDocumentPaymentRequest": "Přidána platební žádost",
    "Delivered": "Doručeno",
    "DeliverCanceled": "Doručení zrušeno",
    "SentByEmail": "Odesláno e-mailem",
    "ReturnedBack": "Vráceno zpět",
    "ChangedKind": "Změněn typ dokladu",
    "SentForSigning": "Odesláno k podpisu",
    "Confirmed": "Potvrzeno",
    "Unconfirmed": "Zrušeno potvrzení",
    "SentFiles": "Odeslány soubory",
    "AddDocumentPaymentOrder": "Přidán platební příkaz",
    "DeleteDocumentPayment": "Odstraněna platba",
    "DeleteDocumentPaymentRequest": "Odstraněna platební žádost",
    "MovedFromOrganization": "Přesunuto z organizace",
    "Split": "Rozděleno",
    "Merged": "Sloučeno",
    "Linked": "Propojeno",
    "SetAccess": "Nastaven přístup",
    "ExpenseTransactionPaired": "Spárována transakce",
    "ExpenseTransactionUnpaired": "Zrušeno spárování transakce",
    "BudgetUpdated": "Aktualizován rozpočet",
    "MovedToOtherOrganization": "Přesunuto do jiné organizace",
    "MovedFromOtherOrganization": "Přesunuto z jiné organizace",
}


def label_for(event_type: str) -> tuple[str, bool]:
    """Return (Czech label, is_verified); a type outside the enum returns the raw type, unverified."""
    if event_type in VERIFIED_LABELS:
        return VERIFIED_LABELS[event_type], True
    if event_type in UNVERIFIED_LABELS:
        return UNVERIFIED_LABELS[event_type], False
    return event_type, False


def unverified_types_in(events: list[dict]) -> set[str]:
    """Raw `type` values in `events` whose label is not verified."""
    result: set[str] = set()
    for event in events:
        _, verified = label_for(event.get("type", ""))
        if not verified:
            result.add(event.get("type") or "(empty type)")
    return result
