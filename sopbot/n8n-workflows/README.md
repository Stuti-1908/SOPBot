# SOPBot n8n Workflows

Export workflow JSON files from n8n and commit them here.
One file per workflow. Use descriptive names.

## Workflows

| File | Description |
|------|-------------|
| `sopbot_main.json` | Main webhook → transcript extract → SOP generation → Drive write → notifications |
| `sopbot_error_handler.json` | Error Trigger → patch Calls Log → ops alert email |

## How to export

1. Open n8n UI → select workflow → menu → Download
2. Save JSON to this directory with the filename above
3. Commit to git: `git add sopbot/n8n-workflows/ && git commit -m "chore: update n8n workflow export"`

## Import on new environment

1. n8n UI → Import → select JSON file
2. Re-enter credentials (they are not exported)
3. Activate the workflow
