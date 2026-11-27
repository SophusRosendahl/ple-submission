# stop: idle
# pull: research/gcp-budget-check.txt
# Read-only: is there a budget, a billing link or a quota on the project that caps our Vertex AI calls? Nothing is changed.
cd ~/ple-submission && git log -1 --oneline
OUT=research/gcp-budget-check.txt
{
  echo "== checked $(date -u +%FT%TZ) by the VM's own service account: $(gcloud config get-value account 2>/dev/null)"
  echo; echo "== billing link of the project"
  gcloud billing projects describe ple-submission 2>&1 | head -12
  BA=$(gcloud billing projects describe ple-submission --format='value(billingAccountName)' 2>/dev/null | sed 's#billingAccounts/##')
  echo; echo "== budgets on billing account '${BA:-unknown}'"
  [ -n "$BA" ] && gcloud billing budgets list --billing-account="$BA" 2>&1 | head -40 || echo "(no billing account id: skipped)"
  echo; echo "== Vertex AI quota overrides on the project (consumer quota)"
  gcloud alpha services quota list --service=aiplatform.googleapis.com --consumer=projects/ple-submission --filter="metric~gemini" 2>&1 | head -40
  echo; echo "== enabled billing-related services"
  gcloud services list --enabled --filter="name~billing OR name~aiplatform" --format="value(name)" 2>&1 | head
} > "$OUT" 2>&1
wc -l "$OUT"; head -30 "$OUT" | cut -c1-200
