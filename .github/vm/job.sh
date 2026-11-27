# stop: idle
# pull: research/rules-models.txt
# Read-only: what do the organizers' public docs say about a harness that calls more than one model (a sub-agent on a different model)?
# Only docs/ and READMEs of the organizers' repository are searched, for lines about models; nothing else is opened.
cd ~/ple-submission && git log -1 --oneline
P=$(ls -d ~/ple /home/*/ple 2>/dev/null | head -1)
{
  echo "== lines in docs and READMEs about declared / more than one / second model, sub-agents, ensembles, must match"
  grep -n -i -H "more than one model\|multiple models\|second model\|another model\|different model\|sub-agent\|subagent\|ensemble\|must match\|declared\|model_api.*match\|only .*model\|single model\|one model\|judge model" "$P"/docs/rules.md "$P"/docs/models.md "$P"/docs/protocol.md "$P"/README.md "$P"/kit/README.md 2>/dev/null | cut -c1-320 | head -60
  echo; echo "== rules.md headings"
  grep -n '^#' "$P"/docs/rules.md 2>/dev/null | head -30
} > research/rules-models.txt 2>&1
cut -c1-240 research/rules-models.txt | head -70
