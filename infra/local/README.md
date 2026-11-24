# Running locally (MacBook)

Tasks run in Docker on your Mac. Models are called on Vertex AI in your Google Cloud project,
through the competition's model proxy, with your own `gcloud` login. You pay only for model
tokens.

## One-time setup

1. **Docker Desktop**, then *Settings → Resources*:
   - CPUs: as many as offered.
   - Memory: as much as you can spare. It decides which tasks can run (below).
   - Disk: at least 150 GB. The seven app-based tasks in half A use large images (about 17 GB
     each, partly shared).
   - *Settings → General*: turn on **Use Rosetta for x86_64/amd64 emulation** (task images are
     x86; this makes them much faster on Apple Silicon).
2. **Tools** (Homebrew):
   ```bash
   brew install uv
   brew install --cask google-cloud-sdk
   uv tool install harbor==0.20.0 --with websockets
   ```
3. **Google Cloud**: Claude Opus 5.5 enabled for your project in Vertex AI Model Garden, then
   ```bash
   gcloud auth application-default login
   gcloud config set project <your-project-id>
   ```
4. **Repositories**, side by side:
   ```bash
   git clone https://github.com/SophusRosendahl/ple.git
   git clone https://github.com/SophusRosendahl/ple-submission.git
   cd ple-submission && git checkout claude/loving-rubin-jc0fnt
   ```

## Each session

```bash
cd ple-submission
bash infra/local/start_proxy.sh          # asks for your Hugging Face token the first time
python3 infra/local/check_models.py      # one text and one image call per model
```

## Running a harness on half A, in batches that fit your memory

`--max-memory-gb` runs only the tasks whose containers fit in what Docker has:

| Docker memory | Tasks that fit |
|---|---|
| 8.5 GB | 3 (`data-hall-mep-routing`, `fire-test-validation-memo`, `data-center-site-model`) |
| 12.5 GB | 13 (all but the two below) |
| 17 GB | all 15 (adds `solar-witness-test-package`, `backfeed-energization-reply`) |

```bash
python3 research/run_dev.py --ple ../ple --entry harnesses/naive \
    --label "rung 0: single model call, files as text" \
    --env-file ../ple/local.env --max-memory-gb 12.5 --trials 1
```

`--trials 1` runs one task at a time, which a laptop needs. If you run the remaining tasks later
(or on a bigger machine), merge the batches into one half-A score:

```bash
python3 research/tracker.py combine run-001 run-002 --label "rung 0, all of half A"
```

Stop the proxy when done: `kill "$(cat ~/ple-proxy.pid)"`.

## Expect

- Emulated x86 containers run slower than on a PC, and the competition docs note that timed
  graders can score a little lower under emulation. Fine for development; note it next to results.
- The first run of an app-based task builds its image (allow an hour or more); later runs reuse it.
