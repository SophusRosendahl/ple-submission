# stop: yes
# pull: research/run-details
# Copy what the two single-task trials produced into research/run-details/ (small files only; no config or lock files).
cd ~/ple-submission
for pair in "run-003:naive-A-20261126-180514" "run-004:naive-A-20261126-181344"; do
  id=${pair%%:*}; dir=${pair##*:}
  T=$(ls -d runs/$dir/attempt1/jobs/dev/data-hall*/ | head -1)
  D=research/run-details/$id; mkdir -p $D
  cp -r "$T/agent" "$T/deliverables" "$T/verifier" $D/ 2>/dev/null
  rm -f $D/agent/egress.log
  echo "$id <- $T"; (cd $D && find . -type f -printf '%s %p\n' | sort -k2)
done
du -sh research/run-details
true
