# Scenario 5: User overview in Excel

Prerequisite: Python with `openpyxl` installed.

## Data collection

1. Organization scope (list / term → confirm).
2. In every organization `list_users` (all pages, compare with `totalItems`) → `get_user` for each user.
   Document type names and the number of types in the organization come from `get_me.documentTypes`.
   Batch because of the rate limit.
3. From `get_user` take: login, name, roles, **real** teams (skip system teams – they are not visible in
   the UI), access to document types split by level.

## Script input

Save JSON (a list of rows, row = user × organization) to the scratchpad:

```json
[
  {
    "login": "jane.novak@company.com",
    "name": "Jane Novak",
    "organization": "Connectify_1",
    "roles": ["Junior Accountant"],
    "teams": ["CFO"],
    "access": {
      "FullAccess": [],
      "All": ["Received invoice", "Issued invoice"],
      "OnlyAssigned": ["Order", "Contract"],
      "NoAccess": ["Internal document"]
    },
    "typeCount": 5
  }
]
```

`NoAccess` = types of the organization the user does not have in `documentTypes`.

## Creating the file

```
python user-management/scripts/build_overview_xlsx.py <input.json> <output.xlsx>
```

The script creates one sheet sorted by user and organization with the columns **User (login), Name,
Organization, Role, Team, Document access**:

- access in one cell, one line per level (`FullAccess: …` / `All: …` / `OnlyAssigned: …` /
  `No access: …`); with FullAccess to all types just `FullAccess: all types (N)`,
- rows of one user share a background color (alternating by user),
- autofilter and a frozen header.

Do not add unrequested sheets or columns (summaries, language, creation dates, permission list). Save the
output where the user says (default: Downloads, file name `wflow-user-overview-<YYYY-MM-DD>.xlsx`).
