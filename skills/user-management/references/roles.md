# Scenario 2: Roles

## Creating via the wizard

Junior Accountant (below) is the only predefined role template; create all other roles with the wizard.

1. Ask about the position's duties. Go through the areas:
   - Processes documents? (creates, edits, attachments, tags, custom fields, inbox; deletes? changes type?)
   - Does accounting / account coding?
   - Handles payments? (payment management, marking for payment)
   - Approves? Reviews? Sends to extraction?
   - Exports to ERP / exports data?
   - Manages settings? (registers, partners, organization settings, access)
2. Propose permissions **by area, including deliberately omitted ones** – omitted permissions matter to the
   user as much as added ones, because they show nothing was forgotten.
3. Propose a short role description (one sentence: what it does and what it does not).
4. Propose the recommended document access by kind.
5. After confirmation: organization scope → check that a role with the same name does not exist in the
   organization yet (if it does, report it and offer an audit/edit instead of creating) → preview →
   `create_role` → verify with `get_role`.

If you need a permission that is not in the table below, take the full list of permission names from
`get_role` of any existing role in the organization.

## Template: Junior Accountant

A Junior Accountant processes and account-codes documents, but does not approve, delete, send to ERP or
change settings.

**Role description:** Document processing and account coding without approval and export.

| Area | Permissions in the role | Deliberately omitted permissions |
| --- | --- | --- |
| Document processing | CanManageDocument, CanManageAttachments, CanManageDocumentLinks, CanManageTags, CanManageCustomProperty, CanAccessInbox | CanDeleteDocument, CanChangeDocumentType |
| Accounting | CanManageDocumentAccounting | CanManagePayments, CanMarkForPayment |
| Workflow | CanSendToExtraction, CanSendToReview, CanReview | CanApprove |
| Export | (none) | CanSendToErp, CanExport |
| Administration | (none) | CanManageRegisters, CanManagePartners, CanManageSettings, CanManageAccess |

**Recommended document access:** All for IncomingInvoice and OutgoingInvoice, OnlyAssigned for other kinds.

## Editing a role

1. `get_role` – load permissions and holders.
2. Add / remove the requested permissions.
3. `update_role` with the **complete** list of permissions **and all original holders** (otherwise they
   lose the role).
4. If the role description no longer matches the permissions (e.g. "without export" and you add
   CanSendToErp), point it out, but do not change the description without an instruction.
5. Verify with `get_role`. Across organizations: preview → confirmation → write → summary.

## Auditing a same-named role

1. Organization scope → in each `list_roles`, find the role by name (report organizations where it is
   missing) → `get_role`.
2. **Standard:** if the skill has a template for the role (Junior Accountant), compare against it.
   Otherwise propose the majority variant (the set of permissions most organizations have) and offer that
   the user can choose a reference organization instead.
3. Output:

   | Organization | Permission count | Deviation from standard | Holders |
   | --- | --- | --- | --- |
   | Connectify_1 | 11 | – | 1 |
   | Connectify_2_wflow | 12 | +CanSendToErp | 0 |

   Below the table, a list of differing permissions by organization (extra / missing).
4. **Do not fix anything without an instruction.** If the user wants a fix, continue as in Editing a role
   (with holders!).
