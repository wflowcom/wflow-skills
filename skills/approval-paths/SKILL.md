---
name: approval-paths
description: "Design, review, export, bulk-edit, create and copy approval paths (approval templates) in wflow.com through the wflow MCP. Four branches: (A) guided design from scratch ending in an Excel of paths and assignment rules, (B) review of the client's own table or written description against wflow know-how, (C) export, audit, search and bulk changes of existing paths, (D) copy paths to another organization. Use whenever the user wants to set up, check, change, export or copy approval paths in wflow, even without saying 'skill'. Trigger phrases: 'approval paths', 'approval templates', 'set up approval', 'design approval paths', 'check our approval table', 'export approval paths', 'which paths is … in', 'replace an approver', 'copy paths to a new company'. Do not use for user or role management or delegation (user-management) or for document work."
---

# Approval paths in wflow

Everything runs as the user signed in to the wflow MCP – what they cannot see, you cannot see.

## Prerequisites

- wflow MCP connected.
- Excel outputs (all branches): Python with `openpyxl` installed.

**Language:** talk to the user in their language (usually Czech or Slovak) and write Excel cell contents in it.
Keep answers short. One question at a time.

## What the MCP can and cannot do

- **Can:** list / read / create / update / delete approval paths, list / create / update teams, list and add
  users, read registers (cost centers, contracts, activities…).
- **Cannot:** read or write workflow automations, i.e. the **assignment rules** that decide which document gets
  which path. Rules are always the client's manual step in wflow; you deliver them as a clear list. Never claim
  you set them.

## The path record

`list_approval_templates` returns only `id`, `name` and `isEmpty`; the levels need one `get_approval_template`
per path, which returns the full record:

- `teams` – list of `{teamId, level}`. Level 1 approves first. **Several entries with the same level = parallel
  approval** (all must approve). A real team on a level = anyone from the team approves.
- `accessTeams` – teams that see the document without approving. wflow stores the teams you send **plus every
  team from `teams`** – send only the extra ones; an empty list is fine.
- `validationLockLevel` – from this level on, a document with a validation error cannot be approved. `null` = no
  lock.
- `conditionFolders` – storage folders the path applies to. Folder ids are organization-specific.

A person placed directly on a level is stored as their **system team** (`system: true`, one member). Its name is
the user's full name and the login is in `description` (name = login only for an account without a name). Find
it with `list_teams` with `query: system = true` and `search: <login>`, then check that `description` matches.
Never add other people to it.

To create a path, call `update_approval_template` without `id` and send `name`, `teams`, `accessTeams`,
`conditionFolders` and `validationLockLevel`. Team names must not contain a comma.

## Start (always)

**0a. What do you want to do?** Skip the menu if the request already makes it clear – confirm in one sentence
and go on.

| Choice | Branch | Reference |
| --- | --- | --- |
| Create approval paths from scratch | **A** – guided design | `approval-paths/references/branch-a-guide.md` |
| I have a table / written description | **B** – review of the input | `approval-paths/references/branch-b-review.md` |
| Check or change paths already in wflow | **C** – export, audit, search, bulk edit | `approval-paths/references/branch-c-existing.md` |
| Copy paths to another (new) organization | **D** – copy | `approval-paths/references/branch-d-copy.md` |

**0b. Beginner or advanced in wflow?** Beginner: explain terms briefly the first time they appear (level, team,
access, assignment rule). Advanced: no explanations unless asked.

**0c. Which organization?** Find it via `list_organizations` (search by what the user says, let them confirm).
In A, if the organization already has paths (`list_approval_templates`), say so and offer C, or ask whether to
keep the existing ones and add new ones next to them.

Then follow the reference for the branch. All branches use:

- `approval-paths/references/know-how.md` – rules you enforce (⛔) and recommend (💡),
- `approval-paths/references/conditions.md` – the 28 assignment conditions, their operators, and the questions
  they map to,
- `approval-paths/references/excel-format.md` – the one Excel format shared by all branches, and its scripts.

## Common rules

1. **Preview and one confirmation before any write.** Show what will be created / changed / deleted, then write
   only after an explicit yes. "I don't understand, show me" is not a yes.
2. **Whole record on update.** `update_approval_template` and `update_team` replace the whole record – omitted
   fields are cleared. Read the current state first and send back everything that should stay: for a path all
   `teams`, `accessTeams`, `conditionFolders` and `validationLockLevel` (without `isEmpty`), for a team its name,
   description and all members. A team you take out of `teams` (person replaced, level removed) stays in the
   `accessTeams` you read – drop it there too, or it keeps seeing every document on the path.
3. **No duplicates.** Before creating a path, check existing names (`list_approval_templates`, all pages, compare
   with `totalItems`). Same name exists → ask: skip, overwrite (with preview), or rename.
4. **People are users of wflow.** Every approver must be a user of the organization. Match people by e-mail
   (`list_users` with `search`). Missing person → offer three options and never silently skip:
   - **add them now** – through the `user-management` playbook if available, otherwise directly with
     `update_user`. Preview + confirmation; say it is a paid license, that wflow e-mails an invitation
     automatically, and that the user needs access to document types (without `documentTypes` they see
     nothing),
   - replace them by someone else,
   - drop the step.
   Do not tell the client to add them by hand and come back.
5. **Do not stop at the skill's border.** If a step belongs elsewhere (missing user, missing cost center or other
   register value, …), offer to solve it right away – via another playbook or directly through the MCP tool –
   with preview and confirmation. Only what the MCP cannot do at all (assignment rules) stays a manual step for
   the client.
6. **Verify after write.** Re-read what you wrote. The create response says `"action":"updated"` even for a new
   path – only the returned id tells you it was created.
7. **Backup before changes to existing paths.** Export the current state (C1) before bulk edits or deletions and
   tell the user where it is.
8. **Rate limit and large organizations.** wflow allows 200 requests/min, returns `429` above it, and the MCP
   does not retry. Batch reads; on `429` wait about 60 s and continue where you stopped. Export, audit and search
   read one `get_approval_template` per path, and an organization can have hundreds of paths: say the count
   (`totalItems`) and the estimate up front – ≈ 4 min per 100 paths with two parallel subagents (≈ 25 paths/min,
   far below the rate limit) – and offer to limit the scope (code prefix, name, selected paths). Delegate the
   reading to subagents by pages of `list_approval_templates`; each checks the number it read against
   `totalItems`.
9. **Assignment rules are the client's job.** End every branch that creates paths with the list of rules to set
   up manually (sheet "Pravidla přiřazení") and say where in wflow: Settings → Workflow automation (Czech UI:
   Nastavení → Automatizace workflow).
10. **Summary at the end.** Short table: what was done, what was skipped and why, errors.
11. **Show results as tables.** Interpretations, proposed paths, findings and previews go in a table, not in
    prose – the user must see exactly what they are confirming. Never ask "is this right?" about something you
    have not shown.
12. **Rights before the first write.** Once you know what will be written, check the person's rights in every
    organization with `get_me`: users → CanManageAccess, teams and approval paths → CanManageApprovalPath,
    register values → CanManageRegisters. Do it before the preview. Exclude organizations where a right is
    missing, list them with the missing right, and never start writing there.

## Do not put in outputs

- System teams as teams – show them as the person.
- IDs in chat unless asked (they belong in the Excel).
- Unrequested sheets, columns or long explanations.
