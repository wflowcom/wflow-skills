# Scenario 1: User onboarding

wflow sends a new user an invitation email automatically – you do not need to mention it.

## Common start

1. Find out the login (email) and the organization scope (list / search term → show → confirm). Do not ask
   for the name – `update_user` accepts only the login; the name comes from the user's account.
2. Verify CanManageAccess of the person running it in every organization (`get_me`). Exclude organizations
   without the permission and list them.
3. In every organization `list_users` with `search` = login. Where the user already exists, report their
   current role and access and do not overwrite them without explicit consent.

## Variant A: manual

1. **Role** – existing (`list_roles` in every organization; if a same-named role is missing somewhere,
   report it), or new via the wizard (`user-management/references/roles.md`).
2. **Document access** – specify by document kind. Default proposal by role (e.g. Junior Accountant:
   All for IncomingInvoice + OutgoingInvoice, OnlyAssigned for the others). When you propose OnlyAssigned,
   explain what it means.
3. **Translation to types** – in every organization take the types from `get_me.documentTypes` and assign
   each type to a level by its kind. List types with unexpected names (e.g. "Development" as a received
   invoice) in the preview.
4. **Teams** – optional; ask whether the user should be in any real team.

## Variant B: by template user ("set up Peter the same as Jane")

1. Find the template user in the selected organizations (`list_users` + `get_user`) and load their roles,
   real teams and access to document types. Where the template user is missing, report it – for that
   organization ask for manual input, or skip it.
2. Do not copy the template user's system teams (`get_user` does not return them). Offer real teams for
   copying, **skip individual teams named after the template user** (Jane_Novak does not belong to Peter) –
   for how to recognize them, see the signals in `user-management/references/delegation-offboarding.md`.
3. Take document access 1:1 by type (types are identical within the same organization).

## Preview (both variants)

Table by organization:

| Organization | Action | Role | Teams | Document access |
| --- | --- | --- | --- | --- |
| Connectify_1 | create | Junior Accountant | – | All: Received invoice, Issued invoice · OnlyAssigned: Order, Contract, … |
| Connectify_3 | skip (already exists) | – | – | – |

Write only after explicit confirmation.

## Writing

1. If a new role is needed, create it first (`create_role`) and verify it.
2. `update_user` (no `id` = new user) with the role, team memberships in `teams` (one call) and **always
   with `documentTypes`** – without them the user sees nothing.
3. Existing user: add team membership via `get_team` → `update_team` with **the original members + the new
   one** (and the original name and description).
4. Verify (`get_user`, `get_team`).
5. Summary by organization (done / skipped and why / errors).
