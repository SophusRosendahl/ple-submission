# Run machine on Google Cloud (optional, not used for now)

We run locally (see `infra/local/`). Keep this for when a laptop is not enough.

One VM in your project runs everything: Docker and the task containers, Harbor, the
competition's model proxy, and our run scripts. Models are called on Vertex AI in the same
project, as the VM's own service account (role `roles/aiplatform.user` only), so no keys are
stored anywhere.

## Before you start

- A Google Cloud project with billing on.
- **Claude Opus 5.5 enabled for the project in Vertex AI Model Garden** (Claude models need their
  terms accepted there once). Check the Gemini 4 models you want are available to the project too.
- A Hugging Face read token with access to `google/physical-engineerings-last-exam`.

## Steps

1. In Cloud Shell, create the VM:
   ```bash
   PROJECT=<your-project-id> bash create_vm.sh     # spot by default; SPOT=0 for on-demand
   ```
2. SSH in (`gcloud compute ssh ple-runner --zone us-central1-a`), copy `setup_vm.sh` over or clone
   `ple-submission`, then run `bash setup_vm.sh` and log out and back in.
3. Clone `ple-submission` (private) next to `~/ple`.
4. Start the model proxy: `bash ple-submission/infra/local/start_proxy.sh` (asks for the Hugging
   Face token once and writes `~/ple/local.env`, readable only by you).
5. Check the models answer, with text and with an image:
   `python3 ple-submission/infra/local/check_models.py`
6. Run a harness on half A:
   ```bash
   cd ~/ple-submission
   python3 research/run_dev.py --ple ~/ple --entry harnesses/naive \
       --label "rung 0: single model call, files as text" --env-file ~/ple/local.env
   ```

## Costs

- VM (default `n2-standard-32` as spot, about 5 tasks at once): roughly 0.4–0.5 USD per hour
  (about 1.5 USD on demand with `SPOT=0`). Google may stop a spot VM; `eval/run.py` re-runs tasks
  that did not finish. The 250 GB disk costs about 25 USD per month while it exists, running or not.
- Model calls are billed by Vertex AI per token. A rung-0 run on half A is 15 single calls plus the
  judge's calls on the rubric tasks.
- **Guards**: the VM powers itself off after 30 idle minutes (no SSH session, no containers, no
  run; `idle_shutdown.sh`) and is stopped after 24 h of running (`MAX_RUN`). The project's budget
  hard cap (`infra/gcp-budget/`) turns off billing entirely at 600 DKK per month.
- Stop it yourself when done: `gcloud compute instances stop ple-runner --zone us-central1-a`.
