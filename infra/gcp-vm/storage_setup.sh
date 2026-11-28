#!/usr/bin/env bash
# One-time, in Cloud Shell (https://shell.cloud.google.com). Safe to run again.
#  1. a Cloud Storage bucket for full run outputs (trajectories, logs, grader output)
#  2. the access the VM (write) and the GitHub workflow (read) need for it, and nothing more
set -euo pipefail
P=ple-submission; REGION=us-central1
N=$(gcloud projects describe $P --format='value(projectNumber)')
BUCKET=ple-runs-$N
VM_SA=ple-runner@$P.iam.gserviceaccount.com
GH_SA=gh-ple-vm@$P.iam.gserviceaccount.com
gcloud config set project $P
gcloud services enable storage.googleapis.com

gcloud storage buckets describe gs://$BUCKET >/dev/null 2>&1 ||
  gcloud storage buckets create gs://$BUCKET --location $REGION --uniform-bucket-level-access
gcloud storage buckets add-iam-policy-binding gs://$BUCKET --member serviceAccount:$VM_SA --role roles/storage.objectAdmin >/dev/null
gcloud storage buckets add-iam-policy-binding gs://$BUCKET --member serviceAccount:$GH_SA --role roles/storage.objectViewer >/dev/null


cat <<MSG

Done. Bucket: gs://$BUCKET
MSG
