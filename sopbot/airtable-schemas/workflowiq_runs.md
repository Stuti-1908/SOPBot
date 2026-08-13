# WorkflowIQ Airtable Schema

Base name: **DadaAI SOPBot** (shared base, separate table)

---

## Table 3: WorkflowIQ Runs

| Field Name                      | Type             | Notes                                      |
|---------------------------------|------------------|--------------------------------------------|
| Run Timestamp                   | Date/time        | UTC, auto-set by app                       |
| Client Name                     | Single line text |                                            |
| SOPs Analysed                   | Number           | Count of SOPs in this run                  |
| Process Names                   | Long text        | Comma-separated process names              |
| Status                          | Single select    | Complete / Error                           |
| Automation Opportunities Found  | Number           | Total across all SOPs                      |
| PDF Filename                    | Single line text | Output PDF filename                        |
| Error Detail                    | Long text        | Populated on error                         |
| Created                         | Created time     |                                            |
