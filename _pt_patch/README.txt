NAKSHATECH ERP - PROJECT TRACKING OPERATIONAL PATCH (v1)
========================================================

TARGET
  E:\nakshatech-erp-shreeyansh1  (or another actual ERP root)

IMPLEMENTED
- Management > Operations > Project Tracking, read-only dashboard.
- Only management role and the two approved Management emails (Vinod and Chethan)
  may call the new backend routes. Frontend routing also checks Management role.
- Department cards from project data and configured ERP technical roles.
- Today / This Month / This Year / Custom Dates / All Time project filters.
- Project register: project/code, client code, PM, details, progress+heatmap,
  description; status & search filtering.
- Survey / file-oriented work: one progress bar from recorded production,
  QC, QA and delivery stages, plus a file/section status heatmap.
- Software projects: one progress bar ONLY; no file/section heatmap.
- Project A-Z details: dates, team, section/file assignments, QC/QA,
  workflow events, paged activity history, and project description.
- Read-only project data Excel/PDF exports, no sales/finance amounts.
- Existing Sales/Finance, Production, QC/QA, Rework and database workflows
  are not rewritten. No migrations, data deletion, or volume removal.
- Original tracking page and original financial endpoint remain on disk;
  the existing URL is mapped to the NEW operational page where detected.

IMPORTANT LIMITATIONS TO VERIFY
- This patch was created from source snapshots of your ERP, NOT from a live
  checkout of your Windows E: drive. Preflight may refuse if files moved.
- Software project milestones/tasks are NOT mapped in the source snapshot.
  Therefore Software progress is "Not tracked" until a real software
  milestone source is integrated. Completed operational workflow status can
  report 100%. No fake 60%/80% milestones are generated.
- Survey percentages are stage-weighted estimates, NOT labor-hour/area
  productivity measurements. Unknown work states are conservatively counted
  as incomplete; completely unknown datasets show "Not tracked".
- Authenticated management email addresses configured in the new route:
  vinod@nakshatech.com, chethan@nakshatech.com. Confirm these match the two
  actual ERP account emails before testing access.
- The dashboard currently reads up to 3000 most recent projects per request.
  Large-scale history/pagination can be added after validating the API.
- PDF/Excel exports match department and status selection but not the current
  free-text browser search; use the exported workbook filter for text.
- No guarantee that previously unrecorded fields will display. Missing info
  is explicitly labeled as not recorded.

APPLY THE PATCH (PowerShell)
  cd "E:\nakshatech-erp-shreeyansh1"
  Expand-Archive -LiteralPath "$env:USERPROFILE\Downloads\NakshaTech_ProjectTracking_Patch_v1.zip" -DestinationPath ".\_pt_patch" -Force
  py -3 ".\_pt_patch\apply_project_tracking_patch.py" --root "." --check
  py -3 ".\_pt_patch\apply_project_tracking_patch.py" --root "." --apply

  IMPORTANT: Read the preflight diff and apply only when it matches your
  current project. A timestamped backup manifest is printed on success.
  Alternative: run .\_pt_patch\APPLY_WINDOWS.ps1

DOCKER TEST
  cd "E:\nakshatech-erp-shreeyansh1"
  .\_pt_patch\RUN_DOCKER_WINDOWS.ps1
  # Requires your existing isolated Docker Compose port override.
  # It does NOT do docker compose down -v.
  # Inspect the actual frontend port in docker compose ps.

VERIFY
  1. Login as Vinod. Open /management/project-tracking.
  2. Click Laser Scanning / Mobile Mapping / Ortho: two indicators.
  3. Click Software Development: only one bar, no heatmap.
  4. Click Details: confirm client code, PM, files and QC/QA history.
  5. Repeat with Chethan. A third non-management account must get 403.
  6. Verify /finance, /finance/sales, Production, QC, QA and rework unchanged.
  7. Export XLSX/PDF and verify NO sales/finance amounts are shown.

ROLLBACK (source files only; database untouched)
  py -3 ".\_pt_patch\apply_project_tracking_patch.py" --root "." --revert "E:\nakshatech-erp-shreeyansh1\.project_tracking_patch_backups\<TIMESTAMP>"
  # Replace <TIMESTAMP> with the printed real backup folder name.
  # Then rebuild backend/frontend using the same Compose config.

The installer refuses to overwrite unrelated files and refuses rollback if
its patched files were edited afterward, preventing accidental data loss.
