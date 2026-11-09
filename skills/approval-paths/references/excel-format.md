# Excel format (shared by all branches)

One format for design (A, B), export (C1), edits (C5) and copies (D), so a client can export, edit and send the
same file back. Sheet and column names are fixed in Czech – the read script and the client's edits depend on
them; write cell contents in the user's language. The English meaning is in brackets.

Build it with `python approval-paths/scripts/build_paths_xlsx.py <input.json> <output.xlsx>`; read client edits
with `python approval-paths/scripts/read_marked_rows.py <file.xlsx>`. If the scripts are not on disk, download
them with `get_playbook(name="approval-paths", file="scripts/<name>")`. Use `python3` where `python` does not
exist. If you cannot run scripts, produce the same layout with whatever spreadsheet tooling you have.

## Sheets

| Sheet | Columns | Used in |
| --- | --- | --- |
| **Cesty** (paths) | Kód (code), Název cesty (path name), Úroveň 1…N (level), Přístup (bez schvalování) (access without approving), Zákaz schválení při validační chybě od úrovně (validation lock from level), Kdy se použije (when used), Poznámka (note), ID cesty (path id, last) | all |
| **Pravidla přiřazení** (assignment rules) | Pořadí (order), Druh / typ dokladu (document kind / type), Kdy přiřadit (when assigned), Podmínky (conditions), → Cesta (path), Poznámka (note) | A, B, D (C only if the client fills it) |
| **Týmy** (teams) | Název týmu (team name), Členové (members), ID týmu (team id) | all |
| **Otevřené otázky** (open questions) | Téma (topic), Otázka (question), Stav (status) | A, B, C5 |
| **Souhrn** (summary) | Položka (item), Hodnota (value) | all |

- A level cell lists its approvers one per line; several lines = parallel approval. A team is written as
  `Tým: <name>`, a person by name (or e-mail if the name is unknown).
- **No fills in data rows.** A coloured row means "changed" (see C5 in
  `approval-paths/references/branch-c-existing.md`); the header row is the only coloured row.
- Only include sheets that are relevant; omit empty ones.

## Input JSON for the build script

```json
{
  "organization": "company",
  "paths": [
    {
      "code": "A0001",
      "name": "A0001: Operations — up to 100,000 CZK",
      "levels": [["Tým: COO"], ["Jane Novak", "Tým: CFO"]],
      "access": ["Tým: Accounting"],
      "validationLockLevel": 2,
      "whenUsed": "Cost center = Operations, Total amount < 100,000",
      "note": "",
      "id": ""
    }
  ],
  "rules": [
    {"order": 1, "documentKind": "Received invoices", "phase": "after extraction",
     "conditions": "Cost center = Operations AND Total amount < 100,000",
     "path": "A0001: Operations — up to 100,000 CZK", "note": ""}
  ],
  "teams": [{"name": "COO", "members": ["John Smith"], "id": ""}],
  "questions": [{"topic": "Limits", "question": "Does exactly 100,000 CZK belong to 'up to' or 'over'?", "status": "open"}],
  "summary": {"Number of paths": 1}
}
```

Keys `rules`, `teams`, `questions`, `summary` are optional – a missing key = the sheet is left out.

## Output of the read script

JSON list of marked rows from sheet "Cesty": `row` (Excel row number), `values` (header → value), `action` =
`create` (no "ID cesty"), `delete` (the word "smazat" in "Poznámka"; "nesmazat" does not count) or `update`.
Coloured rows with no values are skipped.
