# Know-how for approval paths

Rules you enforce (⛔) or recommend (💡). When the user asks why, give the reason.

## The path

- A level holds one user, one team (anyone from the team approves), or several users/teams in parallel (all must
  approve). Levels can be reordered.
- 💡 Substitution belongs in a team, not in a named person. A team with a single member is fine – do not report it
  as a problem.
- Access = people/teams who see the document but do not approve (e.g. controlling).
- A path can forbid approving a document with a validation error from a chosen level on (`validationLockLevel`).
- ⛔ Every approver must be a wflow user of the organization; each user is a paid license, also mobile-only users.
- A user removed from the organization disappears from the paths, also from steps where they were placed
  directly; the validation lock stays on the same level. A level can thus end up without an approver.

## Naming

- 💡 **The name states the conditions the path is assigned by** – it is the quick answer to "why did this document
  get this path". If paths are chosen by cost center and amount, every name contains the cost center and the
  amount.
- 💡 Order of parts follows the decision order: main criterion → exception → amount → creator (when the path is
  assigned by Created by user). Amounts always in one format, e.g. `up to 5,000 CZK`, `5,000–99,999 CZK`,
  `over 100,000 CZK`.
- 💡 With many paths, start with a code: `A0001: …`. The code is the stable key for matching on import and later
  edits, even if the descriptive part changes. Example: `A0008: Commercial — 5,000–99,999 CZK — Jane Novak`
  (Jane Novak = the creator). Do not name paths after their approvers.

## Assignment (automation – the client sets it up)

- Assignment can be manual (per document, also in bulk from the list) or automatic in workflow automation;
  automatic is the usual one.
- A workflow is bound to document types; a path is not. The same path can serve orders and invoices by copying
  the workflow and picking the same path – 💡 **only if it makes sense for the process**, not by default.
- ⛔ One workflow has at most one approval step.
- The path is assigned after receipt, after extraction, or after data check.
- ⛔ ISDOC (and ZUGFeRD/XRechnung) skips the "New document" state, so approval placed "after receipt" never starts
  for them – place it after extraction (or a separate workflow for ISDOC).
- Rules are evaluated top-down, the first match wins → specific rules (exceptions, tags, suppliers) above general
  ones (amount only).
- Suppliers: several conditions possible – Partner, Partner company ID, Partner VAT ID, Partner local VAT ID.
  There is no "new supplier" flag; it needs a list of existing suppliers or a tag.
- 💡 Documents no rule matches stay without a path. Offer either a catch-all path as the last rule, or a custom
  view of documents without an approval path.
- "The creator approves themselves" is always bound to one named person, not a role → several creators = several
  paths.
- 💡 Self-approval up to a limit: recommended that the creator co-approves also above the limit (accountability,
  two signatures in the audit trail). Exception: a manager who is the first level for their team skips their own
  level.
- Contract documents have no cost center → use Created by user instead.
- ⛔ Orders transferred from an ERP have the connector's technical user as creator → they cannot be routed by
  creator; use another field (e.g. contract code filled in the ERP).
- If an automation fills the cost center (header accounting update), it must run before the path is assigned,
  otherwise routing by cost center fails.
- Budget can be a condition: e.g. no budget → separate exceptions path.
