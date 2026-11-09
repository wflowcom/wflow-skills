# Where the skill runs

## Claude Code

Runs on the user's computer. Paths are local; `issued-invoices-import/scripts/pair_pdfs.py <out.json> <pdf-folder>` reads the folder
directly; the PDF upload `command` from `create_file_upload_url` runs with the local file path.

## Cowork

Runs in a cloud container. A file the user attaches is in the container (e.g. under
`/root/.claude/uploads/…`). A folder on the user's computer is reached only through the device tools
(`get_device_info`, `device_request_folder_access`, `device_list_dir`).

### PDF folder

1. Ask for access with the path **exactly as the user wrote it** (full Windows path, e.g. `C:\Users\…\PDF`).
   Do not rebuild it from a home-folder listing. If access fails, ask the user for the path again instead of
   guessing.
2. `device_list_dir` → write the PDF file names, one per line, to `names.txt` in the container.
3. Pair from names: `python issued-invoices-import/scripts/pair_pdfs.py <out.json> --names names.txt`.
   Nothing is copied yet.
4. Ask the PDF question (SKILL.md step 7) from that result.
5. Bring **only the paired PDFs** into the container with the session's device tool that reads files, then
   upload each: `create_file_upload_url` → run its `command` with the container path →
   `upload_document_file`. If no device tool can read files, ask the user to attach the PDFs to the chat.
