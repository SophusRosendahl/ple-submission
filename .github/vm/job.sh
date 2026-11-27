# stop: idle
# pull: research/public-docs-check.txt
# Read-only: do the competition's PUBLIC documents (docs/ and the READMEs of the organizers' repository) state the IFC class / name
# convention (floor panel, containment roof, ...)? Only docs and READMEs are searched; no task, test or grader file is opened.
cd ~/ple-submission && git log -1 --oneline
OUT=research/public-docs-check.txt
P=$(ls -d ~/ple /home/*/ple 2>/dev/null | head -1)
{
  echo "== organizers' repository at $P: top level (names only)"; ls "$P" | head -30
  echo; echo "== docs/ (names only)"; ls "$P/docs" 2>/dev/null | head -40
  echo; echo "== READMEs and docs: lines naming IFC classes, property sets or a naming convention"
  find "$P" -maxdepth 2 \( -iname 'README*' -o -path "$P/docs/*" \) -type f 2>/dev/null | while read f; do
    grep -n -i -H "Pset_DCM\|IfcCovering\|IfcFurniture\|ContainmentRoof\|containment roof\|floor panel\|exact element classes\|naming convention\|dc_model" "$f" 2>/dev/null | cut -c1-260
  done | head -60
  echo; echo "== any dataset card or task-family doc named in the READMEs (names only)"
  grep -rn -i -h "huggingface.co/datasets\|dataset card\|task family\|data hall" "$P"/README* "$P"/docs/* 2>/dev/null | cut -c1-220 | head -15
} > "$OUT" 2>&1
wc -l "$OUT"; head -40 "$OUT" | cut -c1-200
