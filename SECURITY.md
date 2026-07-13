# Security policy

## Reporting a vulnerability

Do not open a public issue for a vulnerability. Use GitHub private vulnerability reporting when available.

Include:

- the affected version or commit;
- reproduction steps;
- expected and observed behaviour; and
- any evidence of data exposure or unsafe workbook mutation.

## Data handling

The core library runs locally and does not transmit workbook or financial data. Integrations that add network access must document their data flow and require explicit configuration.
