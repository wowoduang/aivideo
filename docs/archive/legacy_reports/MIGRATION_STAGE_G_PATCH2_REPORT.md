# Migration Stage G Patch 2 — Pass Validation Empty-Field Semantics Fix

## Problem
Stage G samples returned `status=pass` with valid empty fields:

- `issues: []`
- `safe_rewrite_hint: ""`

The validator incorrectly treated these falsey values as missing fields, causing two valid pass results to fail with `missing_result_fields=["issues", "safe_rewrite_hint"]`.

## Fix
Updated `score_stage_g_item` in `app/services/movie_story/narration_validation_sample.py`:

- `issues` is valid when present as an empty list.
- `safe_rewrite_hint` is valid when present as an empty string for `status=pass`.
- For `status=review` or `status=reject`, `safe_rewrite_hint` still must be non-empty so Stage H can perform safe rewrite.

## Stage Boundary
This patch does not move to Stage H. It only fixes Stage G acceptance semantics.
