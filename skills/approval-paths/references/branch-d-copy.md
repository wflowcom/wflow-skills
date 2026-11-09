# Branch D – copy paths to another organization

Typical case: a new company in a group should approve the same way as an existing one.

## Steps

1. **Source and target(s)** – one or more target organizations; the user must have access to all. Check rights
   in every target (common rule 12 in `approval-paths/SKILL.md`). Which paths: all / by code or name / picked by
   hand.
2. **Read the source** – paths, teams, members.
3. **People** – find each approver in the target by e-mail. For a missing person offer the options from common
   rule 4 in `approval-paths/SKILL.md`: add them to the target right away, replace by someone else (e.g. a
   different director in the new company), or drop the step. Never skip silently and never send the client to do
   it by hand.
4. **Teams** – system teams are people from step 3: use the target user's own system team, never create one.
   Look each other team up in the target with `list_teams` and `search: <name>`. Same name exists → compare
   members; if they differ, ask: use the target team as is, or update it. Not in the target → create it with the
   mapped members.
5. **Names** – offer to replace the company part of the code/name (e.g. `HOLD-` → `TRADE-`).
6. **Duplicates** – a path with the same name in the target → skip / overwrite (with preview) / rename.
7. **Not copied** – assignment rules (the MCP cannot read them; give the client the list to set up in the target)
   and `conditionFolders` (folder ids differ per organization).
8. **Preview → confirmation → write** – teams first, then paths; verify; summary + Excel per
   `approval-paths/references/excel-format.md` for each target.
