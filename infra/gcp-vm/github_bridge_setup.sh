#!/usr/bin/env bash
# One-time, in Cloud Shell (https://shell.cloud.google.com): lets this repo's GitHub Actions drive
# the run VM (.github/workflows/vm.yml) with no stored keys, and writes your Hugging Face token
# into ~/ple/local.env on the VM. Safe to run again.
set -euo pipefail
P=ple-submission; REPO=SophusRosendahl/ple-submission; ZONE=us-central1-a
SA=gh-vm@$P.iam.gserviceaccount.com
gcloud config set project $P
N=$(gcloud projects describe $P --format='value(projectNumber)')
gcloud services enable iamcredentials.googleapis.com sts.googleapis.com
gcloud iam workload-identity-pools describe github --location global >/dev/null 2>&1 ||
  gcloud iam workload-identity-pools create github --location global --display-name GitHub
gcloud iam workload-identity-pools providers describe ple-submission --location global --workload-identity-pool github >/dev/null 2>&1 ||
  gcloud iam workload-identity-pools providers create-oidc ple-submission --location global --workload-identity-pool github \
    --issuer-uri https://token.actions.githubusercontent.com \
    --attribute-mapping google.subject=assertion.sub,attribute.repository=assertion.repository \
    --attribute-condition "assertion.repository=='$REPO'"
gcloud iam service-accounts describe $SA >/dev/null 2>&1 ||
  gcloud iam service-accounts create gh-vm --display-name "GitHub Actions: start, stop and SSH to ple-runner"
for R in roles/compute.instanceAdmin.v1 roles/compute.osAdminLogin; do
  gcloud projects add-iam-policy-binding $P --member serviceAccount:$SA --role $R --condition None >/dev/null
done
gcloud iam service-accounts add-iam-policy-binding ple-runner@$P.iam.gserviceaccount.com \
  --member serviceAccount:$SA --role roles/iam.serviceAccountUser >/dev/null
gcloud iam service-accounts add-iam-policy-binding $SA --role roles/iam.workloadIdentityUser \
  --member "principalSet://iam.googleapis.com/projects/$N/locations/global/workloadIdentityPools/github/attribute.repository/$REPO" >/dev/null

gcloud compute instances start ple-runner --zone $ZONE
read -rsp "Hugging Face read token (new one, with dataset access): " HF; echo
printf '%s' "$HF" | gcloud compute ssh ple-runner --zone $ZONE --command \
  't=$(cat); f=$(ls /home/*/ple/local.env | head -1); sudo sed -i "s|^HF_TOKEN=.*|HF_TOKEN=$t|" "$f" && echo "updated $f"'
unset HF
echo; echo "Done. Tell Claude this project number: $N"
