# Records in the organization's storage (`_Admin`)

The skill stores two things in wflow storage:

- `_Admin/Delegations/delegation-<delegator-login>-<YYYY-MM-DD>.json` – one file per delegation (the
  original state for ending it),
- `_Admin/team-classification.json` – confirmed team classifications (individual / reusable).

Records have **empty rights** → only users with full access (`hasFullAccess`) can see them. Do not add
access for an admin team.

## Consent

Do not create anything in storage without consent. If the `_Admin` folder does not exist in the
organization yet, explain what you want to save and why ("a record of the original state so I can revert
the delegation exactly; the folder will be visible only to admins with full access") and ask. An existing
`_Admin` means consent was already given.

If declined: only print the delegation record in the chat (the user must keep it and hand it over when
ending) and do not save the team classification – ask again next time.

## Writing

1. Find the folders (`list_storage_folder_children` from the root). If they are missing, create `_Admin`
   and `_Admin/Delegations` (`update_storage_folder` without `id`, with `parentId`) and **set both to empty
   rights** (`set_storage_folder_rights` with an empty list) – a new folder otherwise gets Everyone rights.
2. Upload the file: `create_file_upload_url` → PUT the content → `upload_storage_file`. When updating an
   existing record use `overrideIfExists: true` (keeps the `id` and rights).
3. **Set a new file to empty rights** (`set_storage_file_rights`) – a file does not inherit the folder's
   rights and gets Everyone.
4. Verify the rights (`get_storage_folder_rights`, `get_storage_file_rights`) and the content (download and
   decode).

## Reading

`download_storage_file` returns a password-protected AES zip – decode it as described in
`user-management/SKILL.md`, common rule 15.

## Delegation record format

```json
{
  "version": 1,
  "status": "ACTIVE",
  "organization": "connectify-1",
  "delegator": {"login": "peter.smith@company.com", "systemTeamId": "…"},
  "deputy":    {"login": "tom.brown@company.com", "systemTeamId": "…"},
  "reason": "vacation until 2026-10-20",
  "started": "2026-10-06T10:15:00",
  "startedBy": "admin@company.com",
  "ended": null,
  "changes": [
    {
      "type": "template",
      "templateId": "…", "name": "IT invoices",
      "teams": [{"level": 2, "originalTeamId": "<Peter's system team>", "newTeamId": "<Tom's system team>"}],
      "accessTeams": {"mode": "replace", "removed": ["<Peter's system team>"], "added": ["<Tom's system team>"]}
    },
    {
      "type": "team",
      "teamId": "…", "name": "CFO",
      "removedMembers": ["peter.smith@company.com"],
      "addedMembers": ["tom.brown@company.com"],
      "originalDescription": "Chief Financial Officer",
      "newDescription": "Chief Financial Officer | Delegation: Tom Brown for Peter Smith from 2026-10-06"
    }
  ]
}
```

`accessTeams.mode` is `replace` or `add`. The record holds only **the difference the skill made** – on
ending, only the skill's own changes are reverted based on it. On ending set `"status": "ENDED"` and
`"ended"`, and optionally add `"conflicts"` with the list of differences the skill found and left in place.

## Team classification format

```json
{
  "version": 1,
  "teams": {
    "<teamId>": {"name": "CFO", "type": "reusable", "confirmedBy": "admin@company.com", "date": "2026-10-06"}
  }
}
```

`type` is `individual` or `reusable`.
