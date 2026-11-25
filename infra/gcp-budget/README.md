# Budget hard cap

The project's budget ("ple-submission monthly", 600 DKK per calendar month, all services in the
project) emails alerts at 50%, 90%, 100% and 110% (a sign the cut-off was late or failed), plus when spend is forecast to reach 100%. It also
posts to the Pub/Sub topic `budget-alerts`. The Cloud Run function `budget-hard-cap` (europe-west1)
reads each notice and **turns off billing on the project** once actual spend (not the forecast)
reaches the budget.

- **What a cut-off does:** every paid service in the project stops: a running VM is shut down,
  and Vertex AI calls fail. Disks and other data are kept for a while, but Google may delete
  resources if billing stays off for long. A run in progress is lost.
- **It is not exact:** billing data arrives hours late, so spend can go past 600 DKK by a few
  hours' worth before the cut-off.
- **Turn billing back on:** `gcloud billing projects link ple-submission --billing-account 014E2A-DF78C0-BF5687`
  (raise the budget first, or the next notice turns it off again).
- **Change the amount:** `gcloud billing budgets update <budget-id> --billing-account 014E2A-DF78C0-BF5687 --budget-amount 800DKK`
  (the billing account is in DKK; USD amounts are rejected).
- **Permissions:** the function runs as `budget-cap@`, which has only Project Billing Manager
  (enough to unlink billing) and Service Usage Consumer on this project.

Set up or redeploy: `BUDGET_ID=<id> bash setup_hard_cap.sh` (`DRY_RUN=true` to log only). A dry
run was tested on 2026-11-25 with fake notices (700 of 600 DKK: "would disable"; 12.50 of 600: no
action) before switching to live.
