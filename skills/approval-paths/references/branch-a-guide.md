# Branch A – guided design from scratch

Goal: from a client with no approval paths to an Excel with paths and assignment rules, then offer to create the
paths in wflow. Ask **one thing at a time**, from the skeleton to details. Propose a sensible default where you
can ("most clients do X – does it fit you?") instead of open questions.

## Questions

1. **Scope** – which document kinds are approved? Offer: received invoices, issued invoices, orders, contracts,
   receipts, other.
   How do documents arrive (e-mail, ISDOC, ERP connector, mobile)? → decides when the path is assigned (after
   receipt / after extraction / after data check). Watch for ISDOC ("after receipt" never starts) and ERP orders
   (creator = technical user).
2. **Main criterion** – what decides first who approves? Offer the groups from
   `approval-paths/references/conditions.md` (cost center, contract, supplier, amount, creator, document type…).
   This sets the structure of all paths – confirm it before going on.
3. **Values of the main criterion** – offer to load the register from wflow (cost centers, contracts, activities
   via `list_register_*`, users via `list_users`) so the client does not have to type it. For each value: who
   approves?
4. **Amount limits** – thresholds, with or without VAT (Total amount vs. Total amount without VAT), currency.
   What is added above a threshold (another level)? Clarify boundaries: does exactly 100,000 belong to "up to" or
   "over"?
5. **How approval works** – sequential or parallel? Substitutes → propose teams. Self-approval by the creator up
   to a limit? Give the recommendation from `approval-paths/references/know-how.md`.
6. **Exceptions** – suppliers with their own regime (rent, energy…), documents matched to an order, documents
   with a validation error.
7. **Access without approving** – who only needs to see the documents (accountant, controlling)?
8. **Validation lock** – forbid approving with a validation error? From which level?
9. **Documents no rule matches** – catch-all path at the end, or a custom view of documents without a path?
10. **Naming** – with more than a handful of paths propose the convention from
    `approval-paths/references/know-how.md` (code + conditions) with a short reason, and show 2–3 example names
    from their answers.

## Closing

1. **Summary + know-how check** – list the resulting paths and rules; point out problems (rule order, overlaps,
   gaps, missing users, ISDOC / ERP traps).
2. **Excel** – build per `approval-paths/references/excel-format.md` (sheets Cesty, Pravidla přiřazení, Týmy,
   Otevřené otázky, Souhrn). Rule order in "Pravidla přiřazení" = the order the client must set them in wflow.
3. **Offer to create the paths and teams in wflow right away.** On yes:
   - check names against existing paths and check that all people are users (common rules 3 and 4 in
     `approval-paths/SKILL.md`),
   - preview table (path → levels → access → validation lock), one confirmation,
   - create teams first (`create_team`), then paths (`update_approval_template` without `id`, see "The path
     record" in `approval-paths/SKILL.md`),
   - re-read and fill the path ids into the Excel,
   - summary + reminder: assignment rules are set manually in Settings → Workflow automation, following the
     "Pravidla přiřazení" sheet.
