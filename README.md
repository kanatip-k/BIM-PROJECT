# BIM and Navisworks Prototypes

This repository contains experimental BIM data export, MCP integration, web dashboard, and bill-of-quantities workflows.

## Project layout

- `Navisworks_MCP_Web_Prototype/`: the original prototype retained with its existing Git history.
- `agentic-ai-bim-boq/`: proposed addition of the reviewed BOQ prototype, with its own setup and limitations in `README.md`.

The addition is proposed on a separate migration branch. Existing prototype files are preserved; this is not a replacement of the original project.

## Status

Work in progress. Model files, local credentials, generated exports, bundled database runtimes, and operational evidence dumps are excluded from the proposed addition. Regression checks requiring the original CASE2 exports cannot run from the reduced source snapshot without supplying those fixtures locally. Navisworks plugin compilation and end-to-end model extraction have not been validated during migration.

Refer to each prototype's README for requirements and usage. No new license is assigned by the migration.
