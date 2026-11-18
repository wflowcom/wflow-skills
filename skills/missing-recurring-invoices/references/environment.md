# Where the skill runs

## Cowork

Runs in a cloud container. An attached file is in the container (e.g. under `/root/.claude/uploads/…`).
A file on the user's computer is reachable only through the device tools (`get_device_info`,
`device_request_folder_access`, `device_list_dir`) – request access with the path **exactly as the user wrote
it**; if that fails, ask the user to attach the file. The output Excel is saved in the container – offer it as
a download.
