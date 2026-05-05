# Archive

This folder stores legacy reports, migration notes, temporary fix reports, and older design documents.

Current root policy:

- The project root should keep only `README.md` as the documentation entry.
- Current architecture documents should live under `docs/`.
- Historical reports should live under `docs/archive/`.

Important folders:

- `legacy_reports/`: historical migration and fix reports that are still useful for traceability.
- `legacy_design/`: older design notes and architecture drafts.

Deduplication policy used in Stage-O:

- Stage A keeps `MIGRATION_STAGE_A_PATCH2_REPORT.md`; the older Stage A report is removed.
- Stage E keeps `MIGRATION_STAGE_E_PATCH4_REPORT.md`; earlier E reports are removed.
- Stage G keeps `MIGRATION_STAGE_G_PATCH2_REPORT.md`; the older G report is removed.
- Early one-off flow/fix reports were removed when superseded by later hard-fix/debug reports.
