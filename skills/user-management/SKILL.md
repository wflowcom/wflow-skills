---
name: user-management
description: "Manage users and roles in wflow.com via the wflow MCP: user onboarding (manually or by a template user, also across multiple organizations), creating / editing / auditing a role, delegation (starting and ending a substitution), offboarding (removing a user, optionally with a successor) and a user overview in Excel. Use whenever the user wants to add, change or remove a user, role or team member in wflow, even if they don't mention the word 'skill'. Trigger phrases: 'add a user to wflow', 'set up Peter the same as Jane', 'create a role', 'edit a role', 'audit a role', 'delegation', 'she is on vacation, he approves for her', 'end the delegation', 'an employee is leaving', 'remove a user', 'user overview', 'who has access where'. Do not use for creating approval paths (use the approval path import for that), organization settings or working with documents."
---

# User and role management in wflow

All changes run as the user signed in to the wflow MCP – what they cannot see, you cannot see either.

## Prerequisites

- wflow MCP connected.
- Excel overview (scenario 5): Python with `openpyxl` installed.

## Start: choose the scenario

Offer a menu (if the scenario is clear from the request, confirm it in one sentence and continue):

1. **User onboarding** – manually, or by a template user ("the same as Jane"), also across organizations.
2. **Roles** – create via the wizard, edit, audit a same-named role across organizations.
3. **Delegation** – start or end a substitution.
4. **Offboarding** – remove a user, optionally with a successor.
5. **User overview in Excel.**

Bulk import of users from Excel is not supported. If someone asks for it, say so and offer onboarding by a
template user, which works for multiple organizations at once.

Then read the reference for the chosen scenario – it contains the step-by-step procedure:

| Scenario | Reference |
| --- | --- |
| Onboarding | `user-management/references/onboarding.md` |
| Roles (wizard, editing, audit, Junior Accountant template) | `user-management/references/roles.md` |
| Delegation | `user-management/references/delegation-offboarding.md` + `user-management/references/storage-records.md` |
| Offboarding | `user-management/references/delegation-offboarding.md` |
| Excel overview | `user-management/references/excel-overview.md` |

## Key concepts

- **Customer organizations** – the group of organizations of one customer. There is no consistent subdomain
  convention, so the user always specifies the scope (a list or a search term).
- **Role** – a named set of permissions. Each organization has its own copy; same-named roles can differ.
- **System team** – a team with `system: true` and a single member. **Name = the user's full name**
  (e.g. "Kirill Prilepskiy"), **the login is in `description`**; only for an account without a name is the
  name equal to the login. Find it with `list_teams` with `query: system = true` and `search: <login>`
  (searches the description too), then check that `description` matches the login. It represents a user
  placed directly in an approval path. It is not visible in the UI → **never show it in output for the
  user** and never add other people to it. wflow creates it automatically with the user and deletes it with
  them. `get_user` does not return it.
- **Real team – individual** – a regular team named after a person (Peter_Smith).
- **Real team – reusable** – a regular team named after a function (CFO, Purchasing).
- **Document type vs. kind** – each organization has its own types (names, IDs). Kinds are shared:
  IncomingInvoice, OutgoingInvoice, SupplierOrder, Contract, ExpenditureCashSlip, IncomeCashReceipt,
  Other. Define access rules by kind ("All for invoices" = IncomingInvoice + OutgoingInvoice) and translate
  them to the types of each organization.
- **Access level** – FullAccess, All, OnlyAssigned, or no access (type not listed).
  **OnlyAssigned** = the user sees only documents assigned to them (by a step in the approval path or via a
  team). Without an assignment their queue is empty. Whoever should process everything that comes in (e.g.
  an accountant for received invoices) needs All. Explain this to the user whenever you propose OnlyAssigned.
- **accessTeams** – teams in an approval template that automatically get access to the document. A team
  member sees the documents, not just approves them – point this out for delegation.

## Common rules (apply to all scenarios)

1. **The user specifies the organization scope.** `list_organizations` returns hundreds of organizations –
   search by the list or term, show what was found and let the user confirm or narrow it. Do not derive it
   from the subdomain.
2. **Admin permission.** Before a bulk action, verify that the person running it has CanManageAccess in
   every organization in scope (`get_me` per organization). List organizations without the permission up
   front and exclude them – the action must not end halfway.
3. **Document types from `get_me`.** An admin with full access sees all types of the organization (with
   `kind`) in `get_me.documentTypes`. Use `list_document_types` only where the admin lacks full access.
4. **Check before writing.** Before creating, verify that the role / team / user does not exist yet.
   Do not overwrite an existing user without explicit consent, just report it.
5. **Preview and confirmation.** For cross-organization actions, first list what will change where, and
   write only after explicit confirmation. An unclear answer ("I don't understand, show me") is not consent.
6. **Complete data on update.** `update_role`, `update_team` and `update_approval_template` replace the
   whole record. Always load the current state first and send back everything that should stay: for a role
   its holders, for a team its name, description and all members, for a template all `teams`,
   `accessTeams`, `conditionFolders` and `validationLockLevel`. Whatever you omit is deleted.
7. **Removal order:** approval paths → teams → user. No approval level may be left without an approver
   and no empty team may stay in a path (wflow does not handle it in any way).
8. **Verify after writing.** Reload the state after every write. Especially for deletion – the result
   does not return the ID (`delete_user` returns `id: null`, verify with `list_users`).
9. **Document types by kind.** List less obvious types (e.g. "Development" as a received invoice) in the
   preview so the user sees them.
10. **Ask when unclear.** Propose team classification (individual / reusable), organization scope and
    access level and let the user confirm.
11. **Summary at the end.** After a bulk action, a table by organization: what was done, what was skipped
    and why, any errors.
12. **Rate limit.** wflow allows 200 requests/min, above the limit it returns `429` and the MCP does not
    retry. Batch bulk reads; on `429` wait (about 60 s) and continue where you left off – keep track of
    what is done. Do not estimate durations from the limit – real throughput is much lower (see
    `user-management/references/delegation-offboarding.md`, "Finding a person's involvement").
13. **Find a specific team with `search`.** In larger organizations `list_teams` has hundreds of teams
    (sorted alphabetically, paged). For a team by name (COO, CFO…) use `search: <name>` (optionally with
    `query: system = false`) instead of paging; when checking "team does not exist", rely on an empty
    `search` result, not on the first page of the list.
14. **Storage only with consent.** Do not create anything in the organization's storage without consent
    (details in `user-management/references/storage-records.md`).
15. **Reading storage files.** `download_storage_file` returns a password-protected AES zip. Get the
    decoding script with `get_download_archive_format`.

## What not to include in output

- System teams (not visible in the UI, they would confuse the user).
- The language setting of new users – do not address it or mention it.
- Unrequested sheets, columns and summaries in Excel.
