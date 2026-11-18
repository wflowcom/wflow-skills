# Mapping profile

Records how a client's list of regular payments maps to the skill's fields, so the next month needs no
mapping questions. Stored in the organization's wflow storage; the client's list itself is never stored there.

## Where

- Folder **`AI importy`** in the storage root (shared with other import skills). Find it with
  `list_storage_folder_children` (no `folderId` = root).
- File **`profil-pravidelne-faktury.json`**.

Keep both names as they are – saved profiles and the other import skills look them up by these names.

## Read

1. `list_storage_files` with `query: folderId = "<folder id>"`, find the file by name.
2. `download_storage_file` → `downloadUrl` + `zipPassword` – a password-protected AES zip, not the file.
   `unzip` and Python's `zipfile` cannot open it. Download it (`curl -o profile.zip "<downloadUrl>"`), save
   the script from `get_download_archive_format` as `unseal.py` and run
   `python3 unseal.py profile.zip '<zipPassword>' profile/`. Never show the link or the password in chat.

## Write

Only after the user picks "Save the mapping to wflow" in Mode 1, step 6; creating the folder is part of that
confirmation.

1. Save the JSON locally (UTF-8).
2. Folder missing → create it with `update_storage_folder` (`folder: {name: "AI importy"}`, no `id`, no
   `parentId`). A new folder gets Everyone rights → `set_storage_folder_rights` with `teams: []`, then check
   with `get_storage_folder_rights` that the list is empty.
3. `create_file_upload_url` → run the returned `command` with the local file path.
4. `upload_storage_file` with `folderId`, `filename`, `uploadId`; `overrideIfExists: true` when replacing
   (say that the old one is overwritten). Take the file `id` from the result.
5. A new file (not a replacement) does not inherit the folder's rights and gets Everyone rights →
   `set_storage_file_rights` with `teams: []`, then check with `get_storage_file_rights` that the list is
   empty. With empty rights only full-access users see the profile – say so when confirming the save.
6. Verify: `list_storage_files` in the folder shows `profil-pravidelne-faktury.json`.

## Format

```json
{
  "version": 1,
  "name": "Regular payments – finance",
  "updated": "2026-11-13",
  "source": {"sheet": "Regular payments", "headerRow": 1},
  "columns": {
    "name": "Supplier",
    "ic": "Company ID",
    "description": "Description",
    "keyword": null,
    "amount": "Monthly excl. VAT",
    "tolerance": null,
    "frequency": "Frequency",
    "months": null,
    "costCenter": "Cost centre",
    "contract": "Contract",
    "project": null,
    "activity": "Activity",
    "account": "Account"
  },
  "amountWithVat": false,
  "defaults": {"tolerance": 20, "frequency": "M"},
  "dateField": "vatDate"
}
```

- `columns` values are the header texts of the client's file, `null` = not in the file.
- `defaults.frequency` – `M`, `Q` or `Y`, used when the file has no frequency column or the cell is empty.
- `dateField` – the deciding date the user chose last time; offer it as the recommended option next time.
- The profile `template` (no file) = the columns written by `suggest` (Mode 2).
