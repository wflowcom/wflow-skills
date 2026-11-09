# Branch C – existing paths in wflow

> The MCP cannot read automations: you can show **who** approves, not **when** a path is used, and you cannot
> tell whether a path is assigned by any rule. Say so when it matters (export, deletion).

Ask which of these the user wants; for large organizations say the path count and time first (common rule 8 in
`approval-paths/SKILL.md`).

## C1 Overview (export)

Read all paths (`list_approval_templates` + `get_approval_template` each), teams and members (`list_teams`,
`get_team` only for non-system teams the paths use), users (`list_users`) – every list all pages, compare with
`totalItems`. Resolve system teams to people by the login in their `description`. "Přístup (bez schvalování)"
lists only the `accessTeams` that are not in the path's `teams`. Build the Excel per `approval-paths/references/excel-format.md` (Cesty, Týmy, Souhrn); the column "Kdy se
použije" stays empty for the client to fill in. Fill "Kód" from the name if it starts with a code (`A0001:`).

## C2 Search

- "Which paths is Jane Novak in?" – find their system team ("The path record" in `approval-paths/SKILL.md`) and
  every real team they are a member of, then list paths + level where any of these appears. Say whether directly
  or via which team.
- "Who approves path X?" – levels with teams expanded to people.

## C3 Audit

Report only real problems, grouped, each with a suggested fix:

- paths without steps (`isEmpty`),
- empty teams used in paths, levels left without an approver,
- named approvers with no substitute → suggest a team (a team with one member is fine – do not report it),
- duplicate / near-identical paths (same levels, different names),
- inconsistent names → offer the naming convention from `approval-paths/references/know-how.md`,
- inconsistent validation lock across similar paths,
- people present in very many paths (bottleneck).

## C4 Bulk edits in chat

Typical: replace a person, add/remove a level, add access, rename by convention, set the validation lock, delete
unused paths. For a few changes or one change applied everywhere, the chat is faster than Excel – recommend it.

- Person replaced who sits in a **team** → recommend changing the team (one edit) instead of every path.
- Person directly in steps → replace their system team id by the successor's on the same level, and remove the
  old id from `accessTeams` (common rule 2 in `approval-paths/SKILL.md`).
- Removing a level → move the levels below it up by one and shift `validationLockLevel` with them.
- Deleting → warn that a rule may still assign the path (you cannot see it); ask to check in wflow.

## C5 Edits via Excel

For many different changes:

1. The client edits the exported Excel and **colours the changed rows** (any fill colour; one coloured cell marks
   the whole row).
2. A coloured row without "ID cesty" = new path. Deletion = coloured row + "smazat" in "Poznámka" (never by
   deleting the row). A deletion without "ID cesty" → ask which path; never pick one by name.
3. Read marks with `python approval-paths/scripts/read_marked_rows.py <file.xlsx>`. Nothing coloured → ask; never
   assume "all rows".
4. **Check completeness of every marked row and ask before writing.** A new path needs at least a name, approvers
   on each level and "Kdy se použije" (the assignment condition); for changed rows check that nothing required
   was blanked out by mistake. Run the same checks as branch B steps 3–4
   (`approval-paths/references/branch-b-review.md`: users exist, register values exist, naming convention, amount
   boundaries). List what is missing in a table and ask one question at a time – e.g. "The new path A0012 has no
   'Kdy se použije'. What should assign it?" Never write a partially filled path silently. If the client
   explicitly wants to leave a field empty (e.g. rules will be decided later), note it in "Otevřené otázky".
5. Re-read only the marked paths from wflow (detects changes made meanwhile, gives the full record).
6. Preview before → after (deletions highlighted separately), one confirmation, write, verify.

## Safety for C4 / C5

Backup export before changing anything; preview + one confirmation; always send the whole record; summary at the
end.
