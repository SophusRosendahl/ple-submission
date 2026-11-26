#!/usr/bin/env bash
# One-time, in Cloud Shell (https://shell.cloud.google.com). Safe to run again.
#  1. a Cloud Storage bucket for full run outputs (trajectories, logs, grader output)
#  2. a BigQuery dataset for the Cloud Billing export (actual cost per service and day)
#  3. the access the VM and the GitHub workflow need for both, and nothing more
# Enabling the billing export itself is a console step: the script prints it.
set -euo pipefail
P=ple-submission; REGION=us-central1
N=$(gcloud projects describe $P --format='value(projectNumber)')
BUCKET=ple-runs-$N
VM_SA=ple-runner@$P.iam.gserviceaccount.com
GH_SA=gh-ple-vm@$P.iam.gserviceaccount.com
gcloud config set project $P
gcloud services enable storage.googleapis.com bigquery.googleapis.com

gcloud storage buckets describe gs://$BUCKET >/dev/null 2>&1 ||
  gcloud storage buckets create gs://$BUCKET --location $REGION --uniform-bucket-level-access
gcloud storage buckets add-iam-policy-binding gs://$BUCKET --member serviceAccount:$VM_SA --role roles/storage.objectAdmin >/dev/null
gcloud storage buckets add-iam-policy-binding gs://$BUCKET --member serviceAccount:$GH_SA --role roles/storage.objectViewer >/dev/null

bq --location=US show --dataset $P:billing_export >/dev/null 2>&1 || bq --location=US mk --dataset $P:billing_export
gcloud projects add-iam-policy-binding $P --member serviceAccount:$GH_SA --role roles/bigquery.jobUser --condition None >/dev/null
bq add-iam-policy-binding --member serviceAccount:$GH_SA --role roles/bigquery.dataViewer $P:billing_export >/dev/null 2>&1 ||
  echo "(dataset access for $GH_SA: add it in the BigQuery console if this line shows)"

cat <<MSG

Done. Bucket: gs://$BUCKET
Last step, in the console (cannot be scripted): Billing -> Billing export -> BigQuery export ->
"Standard usage cost" -> Edit settings -> project $P, dataset billing_export -> Save.
It only records from the moment it is enabled (no backfill), so do it today.
Tell Claude: "done".
MSG
