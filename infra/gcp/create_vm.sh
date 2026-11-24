#!/usr/bin/env bash
# Creates the run machine in your Google Cloud project. Run it in Cloud Shell
# (https://shell.cloud.google.com), which is already signed in to your account.
#
#   PROJECT=my-project bash create_vm.sh            # on-demand VM
#   PROJECT=my-project SPOT=1 bash create_vm.sh     # spot VM: about a third of the price, can be stopped by Google
#
# What it does:
#   1. enables the Compute Engine and Vertex AI APIs
#   2. creates a service account that may call Vertex AI models (roles/aiplatform.user) and nothing else
#   3. creates the VM with that service account, so the model proxy needs no keys
set -euo pipefail
: "${PROJECT:?set PROJECT to your Google Cloud project id}"
ZONE="${ZONE:-us-central1-a}"
NAME="${NAME:-ple-runner}"
MACHINE="${MACHINE:-n2-standard-32}"   # 32 vCPU, 128 GB: about 5 tasks at once (each needs up to 6 CPU, 16 GB)
DISK_GB="${DISK_GB:-500}"              # task images are large: about 17 GB for each app-based task
SA="ple-runner@${PROJECT}.iam.gserviceaccount.com"

gcloud config set project "$PROJECT"
gcloud services enable compute.googleapis.com aiplatform.googleapis.com

if ! gcloud iam service-accounts describe "$SA" >/dev/null 2>&1; then
  gcloud iam service-accounts create ple-runner --display-name "PLE run machine (Vertex AI only)"
fi
gcloud projects add-iam-policy-binding "$PROJECT" \
  --member "serviceAccount:${SA}" --role roles/aiplatform.user --condition None >/dev/null

SPOT_FLAGS=()
if [[ "${SPOT:-0}" == "1" ]]; then
  SPOT_FLAGS=(--provisioning-model SPOT --instance-termination-action STOP)
fi

gcloud compute instances create "$NAME" \
  --zone "$ZONE" --machine-type "$MACHINE" \
  --image-family ubuntu-2404-lts-amd64 --image-project ubuntu-os-cloud \
  --boot-disk-size "${DISK_GB}GB" --boot-disk-type pd-balanced \
  --service-account "$SA" --scopes cloud-platform \
  "${SPOT_FLAGS[@]}"

cat <<MSG

Created $NAME ($MACHINE, ${DISK_GB} GB) in $ZONE.
Connect:      gcloud compute ssh $NAME --zone $ZONE
Then on the VM: bash setup_vm.sh   (copy it over, or clone ple-submission first)
Stop it when idle (you pay while it runs):
              gcloud compute instances stop $NAME --zone $ZONE
MSG
