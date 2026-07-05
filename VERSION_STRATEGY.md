# MPWRD Dashboard Version Strategy

This repository now maintains two parallel application lines.

## V01 Stable

- Branch: `v01`
- Tag: `v01-stable`
- Purpose: preserve the previously running dashboard exactly as the stable baseline.
- Rule: do not add experimental CWC, bias-correction, hindcast, or downstream-travel logic directly to V01.
- Use V01 for rollback, comparison, and continuity if the enhanced DSS modules need further testing.

## V02 Enhanced DSS

- Branch: `v02`
- Tag: `v02-cwc-dss`
- Current main branch: aligned with V02.
- Purpose: retain all V01 maps, charts, filters, reports, weather, GD site, dam DSS, Water Watch, AI assistant, admin, and export features, while adding the new CWC/GD intelligence layer.
- V02 additions include:
  - CWC historical discharge database
  - GD-CWC station linkage review
  - gauge-to-gauge lead/lag travel-time screening
  - downstream warning-window table
  - hindcast/reforecast intake template
  - baseline bias-correction readiness pipeline
  - V02 pipeline status reporting

## Development Rule

1. Keep V01 intact unless a critical production bug must be fixed.
2. Build new DSS intelligence in V02.
3. If a V01 feature is improved, apply it to V02 as well so V02 remains a superset of V01.
4. Before deploying V02 updates, compare `v01..v02` and confirm changes are additive or intentionally documented.
5. Use `run_v02_bias_pipeline.bat` to refresh V02 CWC/GD/bias assets after any linkage or hindcast update.
6. Run `python scripts/audit_v02_parity.py --v01-ref v01 --v02-ref working-tree` before promoting V02 changes.

## Current Audit

The V02 branch is additive over V01. The only existing V01 app-line change outside new DSS panels is the browser page title, which adds the `V02` version label.

Latest generated parity audit:

- `data/bias_correction/v02_feature_parity_audit.md`
- `data/bias_correction/v02_feature_parity_audit.json`
