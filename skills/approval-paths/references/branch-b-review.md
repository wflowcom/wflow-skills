# Branch B – review of the client's input

Goal: tell the client whether their approval setup is clear and doable in wflow, ask exactly what is missing, and
turn it into the standard Excel.

## Steps

1. **Load the input** – Excel, CSV, or free text / an e-mail description. Inputs come in every shape (matrices,
   one sheet per company, merged cells, roles instead of names).
2. **Interpretation first** – show the user **how the input maps to wflow** and let them confirm **before**
   checking anything. Never ask for a confirmation of something you have not shown, and never guess a mapping you
   are unsure about – mark it with ❓ in the table instead.
   Show, in this order:
   - a table *column in your table → meaning in wflow → example from a row*, e.g.:

     | In your table | In wflow | Example (row 1) |
     | --- | --- | --- |
     | Document | document kind (separate workflow) | Received invoices |
     | Cost center | condition *Cost center* | Cost center = Prague |
     | Amount | condition *Total amount* | "up to 50,000" = less than 50,000 |
     | 1st / 2nd approver | level 1 / 2 of the path | Jane Novak |
     | Notes | additional information | substitute, ISDOC, who the director is |

   - one sentence on what one row is (usually = one approval path + one assignment rule),
   - what happens next (check people and registers in wflow, amount logic, traps, then questions one at a time),
   - a plain-language question, e.g. "Am I reading your table correctly? If so, I'll start checking it against
     wflow." Do not use words like "interpretation" or "mapping" in the question.
3. **Completeness** – for every path: document kind, assignment condition(s), approvers per level, when it is
   assigned.
4. **Check against wflow** (`approval-paths/references/know-how.md`, `approval-paths/references/conditions.md`):
   - every criterion is one of the 28 conditions (or say what replaces it),
   - values exist in the organization's registers (cost centers, contracts… – check via MCP); a missing value →
     offer to create it (common rule 5 in `approval-paths/SKILL.md`), if the register is not synced from the ERP,
   - every approver is a wflow user (by e-mail); a role ("head of department") → who exactly?
   - logic: overlapping rules (need order), gaps (combinations no rule covers), amount boundaries (where does
     exactly 50,000 go?), self-approval, ISDOC and ERP-creator traps,
   - recommendations: substitutes as teams, naming convention, shared paths across document kinds only where the
     process fits.
5. **Findings** in three groups:
   - ✅ clear,
   - ❓ needs input – concrete questions, one at a time when you go through them,
   - ⛔ not possible in wflow – with the alternative.
6. When the open points are resolved → the same closing as A (`approval-paths/references/branch-a-guide.md`:
   Excel + offer to create in wflow).
