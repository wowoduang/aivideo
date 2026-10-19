# Docs tree final sweep round42

## Purpose

Clean up remaining historical documentation residue after the old pipeline cleanup.

This round only touches the documentation tree and empty folders. It does not change runtime code,
prompts, tests for business behavior, or the current three active flows.

## Actions

- Move documentation files whose paths or contents still match removed-pipeline markers to workspace recycle.
- Remove empty documentation folders.
- Add a guard that prevents removed-pipeline names from returning to docs paths.
