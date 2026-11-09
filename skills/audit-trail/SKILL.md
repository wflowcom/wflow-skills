---
name: audit-trail
description: >-
  Generate an audit-trail PDF (event history) for wflow.com documents in the "Sent to ERP"
  (SentToERP) state through the wflow MCP and attach it to each document as a regular attachment.
  Use for: "generate audit trail pdf", "audit trail to wflow", "audit log as PDF",
  "attach audit trail to document", "export document history",
  "vygeneruj auditní stopu", "přilož auditní stopu k dokladu", "export historie dokladu".
---

# Audit trail (PDF) through the wflow MCP

## Prerequisites
- wflow MCP connected.
- A shell (Claude Code or Cowork) — the upload does not work in plain claude.ai chat.
- Python 3 with `reportlab`. If the self-check in step 3 reports it missing, tell the user, install it with
  `$PY -m pip install reportlab` and run the self-check again. If the install fails, stop and show the error
  to the user.
- `curl` (the file upload runs a `curl` PUT).
- A system font with Czech diacritics: Arial, DejaVu Sans or Liberation Sans.

## Rules you NEVER break
1. Always call `upload_document_file` with `main: false`. Never overwrite the document's main file.
2. Never guess the organization: `list_organizations`, the user picks one, use its `subdomain`.
3. Guess nothing: unverified event types and fields are marked in the PDF and you list them in the summary.
4. No stamps, comments or approvals — only the PDF attachment.
5. The result depends on the signed-in user's rights (the MCP runs as that user).
6. Reply in the same language the user writes in, unless told otherwise. If there is no user text to go by
   (e.g. the skill was started by a command alone), reply in Czech.

## Run variables
- `RUN` = `<session scratchpad>/audit-<org>-<YYYYMMDD_HHMM>` (create it in step 3).
- `SCRIPTS` = `$RUN/scripts` — download the helper scripts here. Always call them by absolute path.
- `PY` = the Python 3 command: `python3`; if it does not exist (Windows), `python`.

## Procedure (main agent)
1. **Organization.** `list_organizations` → the user picks one.
2. **Options.** Ask on every run, in this order, even if they were answered earlier in the conversation:
   1. Mode: **a) skip** documents that already have an audit attachment, or **b) add a new version** with a timestamp.
   2. Date to filter by: issue date "Datum vystavení" (`issueDate`), tax point date "Datum UZP" (`vatDate`),
      case date "Datum případu" (`caseDate`), or no date limit.
   3. If a date was chosen: the range FROM/TO in the format DD.MM.YYYY (either end may be left open).
3. **Preparation.** Create `$RUN` and `$SCRIPTS`. Download all four scripts with
   `get_playbook(name="audit-trail", file="scripts/<name>")` and save them in `$SCRIPTS` under the same name:
   `batches.py`, `build_pdf.py`, `event_labels.py`, `property_labels.py` (`build_pdf.py` imports
   both `*_labels.py` files, so they must sit next to it).
   Check the environment: `$PY "$SCRIPTS/build_pdf.py" --self-check` must print `self-check OK`.
   - `reportlab` missing → install it as described in Prerequisites.
   - "No system font with Czech diacritics found…" or any other error → stop and show it to the user.
4. **Documents.** Start one subagent (Agent tool, `model: "opus"`, `subagent_type: "general-purpose"`) to list
   the documents, so the full records stay out of the main context. Its task:
   `list_documents(organization=<org>)` with `query`: `flowStatus = "SentToERP"`. Page through (`pageSize: 100`,
   `page` from 0) until `totalItems` or a page with 0 items. From each item keep only `id`, `number`, `flowStatus`
   and `<date field>` (if one was chosen), and write them to `$RUN/docs.json` (an array of objects). If the server
   rejects `query` (error), repeat the listing **without** `query`. Return only one line: the number of documents
   written, `totalItems`, and whether `query` was used.
   Dates are filtered by the script in step 5.
5. **Batches.** `$PY "$SCRIPTS/batches.py" split "$RUN/docs.json" "$RUN" --size 25 --flow-status SentToERP [--date-field <field> --from FROM --to TO]`
   The script filters status and dates locally; `noDate` is how many documents have no value for the chosen date
   (they are left out). If the server `query` was used, no date range was given and `kept` < `input`, **stop**
   and show it to the user (it means the server filter and the data disagree).
6. **Pre-flight.** Show: organization, number of documents (`kept`), mode, date field and range, number of batches.
   If `noDate` > 0, say that this many documents are left out because they have no value for the chosen date.
   Wait for explicit confirmation.
7. **Subagents.** For each batch `$RUN/batch_NNN.json` start a subagent (Agent tool, `model: "opus"`, `subagent_type: "general-purpose"`), **at most 5 at a time**; start the next wave only after the previous one finishes. The prompt is the template below with the values filled in.
8. **Merge.** `$PY "$SCRIPTS/batches.py" merge "$RUN" "./audit-trail-<org>-<YYYYMMDD_HHMM>.json" --org <org>`
   The log is only a record — idempotence relies on checking the attachments on the server.
   If `missing` is not empty, offer to finish only those documents. In mode **b) new version**, warn the user
   first: a document whose upload went through just before the crash may get a second attachment — let them decide
   whether to run the retry. Then write `missing` from the merge output to `$RUN/missing.json`, then
   `$PY "$SCRIPTS/batches.py" split "$RUN/missing.json" "$RUN/retry" --size 25 --flow-status ""`.
   Subagents (same template, same mode) get `batch: $RUN/retry/batch_<NNN>.json` and
   `results: $RUN/results_r<NNN>.jsonl`. Then run merge on `$RUN` again (same log path).
9. **Summary.** Generated / skipped / errors (with document numbers) / unverified event types
   and unverified fields. For unverified ones, ask the user to compare the PDF with the "Events" panel
   ("Události" in the Czech UI). Then delete `$RUN` (the log in the current directory stays).

## Subagent prompt template

```
Process a batch of documents for the wflow audit trail. Work on your own, ask nothing.
organization: <org>
mode: <skip|version>
batch: <RUN>/batch_<NNN>.json   (array of {id, number})
results: <RUN>/results_<NNN>.jsonl
working folder: <RUN>/w_<NNN>/ (create it)
python: <PY>
scripts: <SCRIPTS>   (call them by absolute path; the environment is already checked, install nothing)

For each document {id, number} in order:
1. mcp list_document_files(organization, documentId=id) → save the result to <RUN>/w_<NNN>/files.json.
2. Run: <PY> "<SCRIPTS>/build_pdf.py" name --number "<number>" --id "<id>" --mode <mode> --files "<RUN>/w_<NNN>/files.json"
   Output SKIP → <PY> "<SCRIPTS>/batches.py" record "<results>" --id <id> --number "<number>" --status skipped_exists ; continue with the next document.
   Otherwise the output is the attachment NAME.
3. mcp get_document(organization, documentId=id) and mcp list_document_events(organization, documentId=id).
   Write <RUN>/w_<NNN>/in.json = {"org": "<org>", "document": <detail>, "events": <events>}, where <detail>
   contains only these fields from get_document: number, internalCode, partnerName, totalAmount, currency, issueDate,
   dueDate, flowStatus.
   Keep the "info" field of the events exactly as it came (do not parse, do not translate).
4. <PY> "<SCRIPTS>/build_pdf.py" render "<RUN>/w_<NNN>/in.json" "<RUN>/w_<NNN>/<NAME>"
   → JSON {events, unverifiedTypes, unverifiedProperties}.
5. mcp create_file_upload_url(organization) → run the returned `command` (curl PUT), sending
   the file <RUN>/w_<NNN>/<NAME> as the body (change only the file path in the command, keep
   the headers). Then mcp upload_document_file(organization, documentId=id, filename=<NAME>,
   uploadId=<uploadId>, main=false). Use each uploadId only once; if upload_document_file
   fails, retry with the same uploadId once more, then record it as an error.
   Then mcp list_document_files(organization, documentId=id) and check that a file named <NAME> is there;
   if it is not, record it as an error.
6. <PY> "<SCRIPTS>/batches.py" record "<results>" --id <id> --number "<number>" --status generated --attachment "<NAME>" --events <events> --unverified-types "<a,b>" --unverified-properties "<x,y>"
7. Delete <RUN>/w_<NNN>/in.json and the PDF.
An mcp call answered with 429 (rate limit): wait about 60 s and repeat the same call, up to 3 times; after that it is an error.
Any error on a document: <PY> "<SCRIPTS>/batches.py" record "<results>" --id <id> --number "<number>" --status error --error "<short text>" and continue with the next one.
Never call upload with main=true, never delete files in wflow.
At the end return ONLY one line: "batch <NNN>: generated X, skipped Y, error Z". No event data.
```
