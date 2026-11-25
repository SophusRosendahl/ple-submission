#!/usr/bin/env bash
# Budget hard cap for the project: the budget posts to a Pub/Sub topic, and a Cloud Run function
# turns off billing on the project once actual spend reaches the budget amount.
#
#   BUDGET_ID=<id> bash infra/gcp-budget/setup_hard_cap.sh            # live
#   DRY_RUN=true BUDGET_ID=<id> bash infra/gcp-budget/setup_hard_cap.sh   # logs only
#
# Re-running is safe. Billing data lags by hours, so spend can still pass the cap a little.
# After a cut-off: gcloud billing projects link $PROJECT --billing-account $BILLING_ACCOUNT
set -euo pipefail
PROJECT="${PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
BILLING_ACCOUNT="${BILLING_ACCOUNT:-$(gcloud billing projects describe "$PROJECT" --format='value(billingAccountName)' | cut -d/ -f2)}"
: "${BUDGET_ID:?set BUDGET_ID (gcloud billing budgets list --billing-account $BILLING_ACCOUNT)}"
REGION="${REGION:-europe-west1}"
TOPIC=budget-alerts
SA="budget-cap@$PROJECT.iam.gserviceaccount.com"
TRIGGER_SA="$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')-compute@developer.gserviceaccount.com"
DIR="$(cd "$(dirname "$0")" && pwd)"

gcloud services enable pubsub.googleapis.com cloudfunctions.googleapis.com run.googleapis.com \
  cloudbuild.googleapis.com artifactregistry.googleapis.com eventarc.googleapis.com \
  cloudbilling.googleapis.com billingbudgets.googleapis.com cloudresourcemanager.googleapis.com \
  --project "$PROJECT"

gcloud pubsub topics describe "$TOPIC" --project "$PROJECT" >/dev/null 2>&1 \
  || gcloud pubsub topics create "$TOPIC" --project "$PROJECT"

gcloud iam service-accounts describe "$SA" --project "$PROJECT" >/dev/null 2>&1 \
  || gcloud iam service-accounts create budget-cap --project "$PROJECT" \
       --display-name "Budget hard cap (can only unlink billing from this project)"
# Project Billing Manager on this project only: enough to unlink billing, nothing else.
gcloud projects add-iam-policy-binding "$PROJECT" --member "serviceAccount:$SA" \
  --role roles/billing.projectManager --condition None >/dev/null
# Lets it call APIs (Cloud Billing, Resource Manager) on this project's quota; grants no resource access.
gcloud projects add-iam-policy-binding "$PROJECT" --member "serviceAccount:$SA" \
  --role roles/serviceusage.serviceUsageConsumer --condition None >/dev/null

gcloud functions deploy budget-hard-cap --gen2 --project "$PROJECT" --region "$REGION" \
  --runtime python312 --source "$DIR/function" --entry-point stop_billing \
  --trigger-topic "$TOPIC" --service-account "$SA" --trigger-service-account "$TRIGGER_SA" \
  --set-env-vars "TARGET_PROJECT_ID=$PROJECT,DRY_RUN=${DRY_RUN:-false}" \
  --memory 256Mi --max-instances 1

gcloud billing budgets update "$BUDGET_ID" --billing-account "$BILLING_ACCOUNT" \
  --notifications-rule-pubsub-topic "projects/$PROJECT/topics/$TOPIC"
echo "hard cap active on $PROJECT (dry_run=${DRY_RUN:-false})"
