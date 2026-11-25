#!/usr/bin/env bash
# Creates the run machine in your Google Cloud project. Run it in Cloud Shell
# (https://shell.cloud.google.com), which is already signed in to your account.
#
#   PROJECT=my-project bash create_vm.sh            # spot VM (default): about a third of the price, can be stopped by Google
#   PROJECT=my-project SPOT=0 bash create_vm.sh     # on-demand VM
#
# What it does:
#   1. enables the Compute Engine and Vertex AI APIs
#   2. creates a service account that may call Vertex AI models (roles/aiplatform.user) and nothing else
#   3. creates the VM with that service account, so the model proxy needs no keys
#
# Cost guards: the VM powers itself off after 30 idle minutes (idle_shutdown.sh), and Google
# stops it after MAX_RUN of running time whatever it is doing (a stopped VM costs only its disk).
set -euo pipefail
: "${PROJECT:?set PROJECT to your Google Cloud project id}"
ZONE="${ZONE:-us-central1-a}"
NAME="${NAME:-ple-runner}"
MACHINE="${MACHINE:-n2-standard-32}"   # 32 vCPU, 128 GB: about 5 tasks at once (each needs up to 6 CPU, 16 GB)
DISK_GB="${DISK_GB:-250}"              # task images: about 17 GB per app-based task, partly shared; half A fits
MAX_RUN="${MAX_RUN:-24h}"              # hard stop per start; a half-A run with 6 h task limits fits
SA="ple-runner@${PROJECT}.iam.gserviceaccount.com"

gcloud config set project "$PROJECT"
gcloud services enable compute.googleapis.com aiplatform.googleapis.com

if ! gcloud iam service-accounts describe "$SA" >/dev/null 2>&1; then
  gcloud iam service-accounts create ple-runner --display-name "PLE run machine (Vertex AI only)"
fi
gcloud projects add-iam-policy-binding "$PROJECT" \
  --member "serviceAccount:${SA}" --role roles/aiplatform.user --condition None >/dev/null

SPOT_FLAGS=()
if [[ "${SPOT:-1}" == "1" ]]; then
  SPOT_FLAGS=(--provisioning-model SPOT)
fi

gcloud compute instances create "$NAME" \
  --zone "$ZONE" --machine-type "$MACHINE" \
  --image-family ubuntu-2404-lts-amd64 --image-project ubuntu-os-cloud \
  --boot-disk-size "${DISK_GB}GB" --boot-disk-type pd-balanced \
  --service-account "$SA" --scopes cloud-platform \
  --max-run-duration "$MAX_RUN" --instance-termination-action STOP \
  --metadata-from-file startup-script="$(dirname "$0")/idle_shutdown.sh" \
  "${SPOT_FLAGS[@]}"

cat <<MSG

Created $NAME ($MACHINE, ${DISK_GB} GB) in $ZONE.
Connect:      gcloud compute ssh $NAME --zone $ZONE
Then on the VM: bash setup_vm.sh   (copy it over, or clone ple-submission first)
It powers off after 30 idle minutes and after $MAX_RUN of running; start it again with
              gcloud compute instances start $NAME --zone $ZONE
Stop it yourself when done (you pay while it runs):
              gcloud compute instances stop $NAME --zone $ZONE
MSG
