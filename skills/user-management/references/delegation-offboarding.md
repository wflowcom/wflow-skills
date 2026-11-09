# Scenarios 3 and 4: Delegation and offboarding

The procedure depends on **how the person is involved in approval**. One person can be involved differently
in different paths (directly in one = situation 1, via the CFO team in another = situation 3). Determine the
situation **for each involvement separately** and combine the procedures.

## Decision table

| Situation | How to recognize it | Delegation (temporary) | Offboarding (permanent) |
| --- | --- | --- | --- |
| **1. User only** | The template contains their system team (`system: true`, login in `description`). | The deputy **replaces** the delegator in `teams` on the same levels. In `accessTeams` let the user choose: replace (default), or add the deputy alongside. | Replace with the successor on the same levels (in `teams` and `accessTeams`), or remove if there is no replacement. Then delete the user. |
| **2. Individual team** (Peter_Smith) | A real team named after a person, usually 1 member. | The deputy is added to the team, the delegator is temporarily removed. Paths do not change. | Create a new team for the successor (John_Brown), replace the old team with it in templates (`teams` and `accessTeams`) on the same levels, delete the old team, delete the user. |
| **3. Reusable team** (CFO) | A real team named after a function. | The deputy is added to the team, the delegator is temporarily removed. Paths do not change. | The team stays, the member is swapped (leaver out, successor in). Then delete the user. Without a successor see below. |

**The deputy replaces the delegator, they are not added alongside.** The delegator does not approve
during the delegation.

### Individual or reusable team?

Estimate the type from the signals, show the reason in the preview and **always let the user confirm** the
classification:

| Signal | Estimate |
| --- | --- |
| The name matches a member's name or login (without diacritics, any word order, `_` or space) | Individual |
| The name is a function or department (CFO, Purchasing, Approver_IT…) | Reusable |
| The team has more than one member | Reusable |
| The team has one member and the name matches nobody | Unclear → ask |

Save the confirmed classification to `_Admin/team-classification.json` (with consent, see
`user-management/references/storage-records.md`). Before asking, check whether the classification is
already there.

### Where a team is replaced

Before deleting or replacing a team, find and replace it **only in approval templates** (`teams` and
`accessTeams`), only then delete the old team. Do not go through rights on storage folders or on
individual documents.

### The deputy / successor must exist

…in the organization and have a role with CanApprove. If not, report it and offer to add them first
(onboarding; for offboarding by the leaver as the template user).

### Warnings that must appear in the preview

- **Removal without replacement** (situations 1 and 2): if they were alone on the level, the level
  disappears and approval gets shorter.
- **accessTeams:** a team member also sees the documents, not just approves them – the deputy gains access.
- **Reusable team without a successor** (situation 3, the leaver is the only member): the team would stay
  empty, which wflow does not handle and must not remain in a path. Offer:
  1. **A temporary team member (recommended)** – a manager / colleague from the same level. Paths do not
     change; when the successor starts, only the member is swapped.
  2. **Removing the team from paths** – the level disappears. Keep the empty team for a future successor,
     or delete it.

  Do not remove the leaver from the team without the user's decision.

## Finding a person's involvement

1. `get_user` → the person's real teams (`get_team` for member count and description).
2. The person's system team: `list_teams` with `query: system = true` and `search: <login>` → verify that
   `description` matches the login.
3. **Recently created user:** a system team gets into paths only by manual addition. If the user was
   created in the organization recently (`created` from `get_user`, e.g. today), offer skipping the template
   scan as the recommended option and handle only their real teams; leave the full scan as the user's choice.
4. `list_approval_templates` (all pages, compare with `totalItems`). It returns only `id`, `name` and
   `isEmpty` and cannot filter by team, so the detail of every template must be loaded. Tell the user the
   number of templates and the estimated duration up front: ≈ 4 min per 100 templates with two parallel
   subagents (≈ 25 templates/min, far below the rate limit). Offer narrowing the organizations.
5. Delegate the scan to subagents (Agent tool) by pages of `list_approval_templates` (e.g. pages 0–4 and
   5–9 of 100). Give each one: the searched `teamId`s (the person's system team, the deputy's / successor's
   system team, the person's real teams); output = template, level, number of teams on the level,
   occurrence in `accessTeams`; and a check of the number read against `totalItems`. Each subagent calls
   `get_approval_template` per template (batched, wait on `429`).
6. For each occurrence determine situation 1/2/3 and whether it is alone on its level.
7. **Reuse the scan result within the session** (e.g. delegation → offboarding of the same person in the
   same organization). Before writing, only reload the affected teams / templates; do not repeat the whole
   scan unless the user asks for it.

## Delegation – start

1. Find out the delegator, the deputy, the organizations and optionally the reason/end date (only for the
   record – the MCP cannot schedule an action for a date, ending is triggered on request).
2. Verify `hasFullAccess` of the person running it (`get_me`) – only an admin with full access may start
   and end a delegation, because only they can see the storage record.
3. Verify the deputy (exists, has CanApprove).
4. Find the involvement (see above), determine the situations and let the user confirm. For situation 1
   ask about `accessTeams` (replace / add alongside).
5. Ask for consent to save the record (if `_Admin` does not exist yet).
6. Preview of changes by organization and template / team. After confirmation:
   - **save the record first** with the original state (`user-management/references/storage-records.md`) –
     if writing the changes ends halfway, the record is the only way back;
   - situation 1: `get_approval_template` (fresh) → in `teams` swap the `teamId` of the delegator's system
     team for the deputy's system team on the same level; `accessTeams` per the choice →
     `update_approval_template` with the complete content;
   - situations 2 and 3: `get_team` → `update_team` with members (− delegator, + deputy), the original
     name and the description extended with the note `Delegation: <deputy> for <delegator> from <YYYY-MM-DD>`.
7. Verify by reloading, update the record with the changes actually made, show the summary **and the whole
   record in the chat** as a backup.

## Delegation – end ("end Tom's delegation for the CFO")

1. Verify `hasFullAccess`. Find the record in `_Admin/Delegations` with status `ACTIVE` (or get it from the
   user from the chat if it was not saved). Load it with `download_storage_file` and decode it (see
   `user-management/SKILL.md`, common rule 15).
2. For each change in the record, load the current state and compare it with what the skill set at the start.
3. **Conflict:** if the current state differs (someone changed the team/path in the meantime), report it,
   show the difference (saved × current) and revert **only the skill's own changes**: remove the deputy
   where the skill added them, return the delegator where the skill removed them. Leave other changes.
4. Remove the delegation note from the team description (keep the rest of the description).
5. Preview → confirmation → write → verification.
6. Overwrite the record (`overrideIfExists: true`) with status `ENDED` and the end date. Do not delete it –
   it serves as history.

## Offboarding

1. Find all organizations in scope where the leaver is (`list_users` with `search`).
2. In each, find the involvement (see above).
3. Determine the situations, let the user confirm and ask about the successor (can differ by organization /
   team).
4. If the successor is not in the organization, offer to add them – onboarding with the leaver as the
   template user. wflow creates the successor's system team automatically, so they can be placed in paths
   right away.
5. Documents in progress – only for situation 1 (see below).
6. Preview: changes in paths, teams, deletion of teams and the user. Point out levels that will disappear
   and teams that would stay empty.
7. After confirmation, **in the order paths → teams → user**:
   - paths: replacing / removing the system team (situation 1) and the old individual team (situation 2,
     after creating the successor's new team via `create_team`);
   - teams: swapping the member (situation 3), deleting the old individual team (situation 2) – only once
     it is in no template;
   - user: `delete_user` → verify via `list_users` (the result returns `id: null`).

   Deleting the user is fine: the history and audit trail of documents remain, the system team is deleted
   with them.
8. Summary by organization.

## Documents in progress (situation 1 – delegation and offboarding)

Nothing needs to be done for teams (situations 2 and 3) – the member swap applies to documents in progress
too. For a user directly in a path, a document in progress keeps waiting for the original user:

1. Tell up front how many documents you will check (`totalItems`) and offer narrowing (e.g. last 6 months,
   selected types).
2. Candidates: `list_documents` with `query` `approvalStatus = "NotApproved" and removed = null`
   (+ any narrowing). For each, `get_document_approvals` – look for the person's system team on a level that
   is not approved yet. Batch because of the rate limit.
3. List them (number, partner, amount, level) with instructions: in the UI delete the approval path on the
   document and apply it again – **approvals already made are deleted by this**.
4. Do not change anything on the documents.
