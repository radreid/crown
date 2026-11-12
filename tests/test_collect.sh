#!/usr/bin/env bash
# crown local collect: the read-only collection path, and review check's strict gate for
# collected records, on throwaway runs. The legacy checker behavior for member-written
# records is asserted unchanged at the end. Run: tests/test_collect.sh
set -u
cd "$(dirname "$0")/.." || exit 1
# shellcheck source=hermetic.sh
. tests/hermetic.sh
T=$(mktemp -d); trap 'rm -rf "$T" "$HERMETIC"' EXIT; fail=0
export CROWN_CONF=$T/c CROWN_STATE=$T/s CROWN_RUN_TMP=$T
ok() { echo "ok   $1"; }; no() { echo "FAIL $1"; fail=1; }
git init -q -b main "$T/r" && printf 'a\nb\nc\n' > "$T/r/names.txt" && git -C "$T/r" add names.txt && git -C "$T/r" -c user.name=t -c user.email=t@example.net commit -q -m one
git init -q --bare "$T/remote.git" && git -C "$T/r" remote add origin "$T/remote.git" && git -C "$T/r" push -q origin main
mkdir -p "$T/c/projects"
jq -n --arg p "$T/r" '{schema:1,project:"rproj",repo:{url:"https://github.com/example/rproj",path:$p,long_lived:["main"]},roles:{build:{base:"main",push:{mode:"none"}}},models:{provider:{local:"claude-code",cloud:"claude-platform"}},memory:{},budget_cents:500}' > "$T/c/projects/rproj.json"
newrun() { ./bin/crown local prepare --repo "$T/r" --base main --slug "$1" --scratch "$T" --role review | sed -n '1,/^$/s/^RUN=//p'; }
taskblock() { printf 'TASK: count the lines of names.txt and state the count\nDONE: test $(wc -l < names.txt) -eq 3\nBASE: main\n' >> "$1/task.md"; }

# a BLOCKED response in the contract's format collects as BLOCKED and passes the strict gate
A=$(newrun cola); taskblock "$A"
cat > "$A/out/transcript" <<'EOF'
BLOCKED: the sandbox kept OUT read-only, so the report pair could not be written

Files changed: none
Deviations: none
Noticed, not acted on: nothing
EOF
out=$(./bin/crown local collect "$A" 2>&1); rc=$?
[ $rc = 0 ] && [ "$(jq -r .status "$A/out/manifest.json")" = BLOCKED ] && ok "a BLOCKED response collects as BLOCKED" || no "collect BLOCKED (rc=$rc): $out"
[ "$(jq -r .collection.provenance.blocked_reason "$A/out/manifest.json")" = member-stated ] && ok "blocked_reason is graded member-stated" || no "blocked_reason grade"
[ "$(jq -r .collection.source.sha256 "$A/out/manifest.json")" = "$(sha256sum "$A/out/transcript" | cut -d' ' -f1)" ] && ok "the manifest records the captured response's hash" || no "source hash"
[ "$(jq -r .done.exit_code "$A/out/manifest.json")" = 0 ] && [ "$(jq -r '.collection.provenance.done.grade' "$A/out/manifest.json")" = crown-verified ] \
  && ok "done is the collector's own re-execution, graded crown-verified" || no "done re-execution"
out=$(python3 lib/review_check.py "$A/out" 2>&1); rc=$?
[ $rc = 0 ] && grep -q 'OK collected read-only run: status BLOCKED' <<<"$out" && ok "review check passes the collected BLOCKED record on the strict path" || no "strict gate BLOCKED (rc=$rc): $out"

# a DONE response collects as DONE and passes
B=$(newrun colb); taskblock "$B"
cat > "$B/out/transcript" <<'EOF'
DONE

DONE check: `test $(wc -l < names.txt) -eq 3` — exit 0
Files changed: none
Noticed, not acted on: nothing
EOF
./bin/crown local collect "$B" >/dev/null 2>&1 && [ "$(jq -r .status "$B/out/manifest.json")" = DONE ] && ok "a DONE response collects as DONE" || no "collect DONE"
python3 lib/review_check.py "$B/out" >/dev/null 2>&1 && ok "review check passes the collected DONE record" || no "strict gate DONE"

# an informal response collects as INCOMPLETE, and INCOMPLETE never passes
C=$(newrun colc); taskblock "$C"
printf 'names.txt has 3 lines. I changed nothing.\n' > "$C/out/transcript"
./bin/crown local collect "$C" >/dev/null 2>&1 && [ "$(jq -r .status "$C/out/manifest.json")" = INCOMPLETE ] && ok "an informal response collects as INCOMPLETE" || no "collect INCOMPLETE"
out=$(python3 lib/review_check.py "$C/out" 2>&1); rc=$?
[ $rc = 1 ] && grep -q 'INCOMPLETE never passes\|record is INCOMPLETE' <<<"$out" && ok "review check refuses an INCOMPLETE record" || no "strict gate INCOMPLETE (rc=$rc): $out"

# a deposited in-session response collects the same way (kind session)
D=$(newrun cold); taskblock "$D"
cat > "$D/response" <<'EOF'
DONE

DONE check: `test $(wc -l < names.txt) -eq 3` — exit 0
Files changed: none
Noticed, not acted on: nothing
EOF
printf '{"runtime":"claude-code","model":"test-model"}' > "$D/response.source.json"
./bin/crown local collect "$D" >/dev/null 2>&1 && [ "$(jq -r .collection.source.kind "$D/out/manifest.json")" = session ] \
  && cmp -s "$D/response" "$D/out/response" && [ "$(jq -r .environment.model "$D/out/manifest.json")" = test-model ] \
  && ok "a deposited session response collects with its bytes preserved and its source recorded" || no "collect session deposit"
python3 lib/review_check.py "$D/out" >/dev/null 2>&1 && ok "review check passes the session-collected record" || no "strict gate session"

# tampering with the preserved response after collection fails the gate
cp -r "$A/out" "$T/tampered" && printf 'x' >> "$T/tampered/transcript"
out=$(python3 lib/review_check.py "$T/tampered" 2>&1); rc=$?
[ $rc = 1 ] && grep -q 'SHA-256 does not match' <<<"$out" && ok "a tampered preserved response fails the strict gate" || no "tamper gate (rc=$rc): $out"
# a collected record without its report fails the gate (the pair is validated together)
cp -r "$A/out" "$T/noreport" && rm "$T/noreport/report.md"
python3 lib/review_check.py "$T/noreport" >/dev/null 2>&1 && no "a collected record passed without its report" || ok "a collected record without its report fails the strict gate"

# the refusals: a member-written pair is never replaced; a write run is the harvest's ground; no capture, no collection
E=$(newrun cole); taskblock "$E"; printf '# member report\n' > "$E/out/report.md"
out=$(./bin/crown local collect "$E" 2>&1); rc=$?
[ $rc != 0 ] && grep -q 'member-written' <<<"$out" && [ "$(cat "$E/out/report.md")" = '# member report' ] && ok "collect refuses a run holding a member-written report, untouched" || no "refuse member pair (rc=$rc): $out"
F=$(./bin/crown local prepare --repo "$T/r" --base main --slug colf --scratch "$T" | sed -n '1,/^$/s/^RUN=//p'); taskblock "$F"; printf 'DONE\n' > "$F/out/transcript"
out=$(./bin/crown local collect "$F" 2>&1); rc=$?
[ $rc != 0 ] && grep -q 'counterpart of harvest' <<<"$out" && ok "collect refuses a write run" || no "refuse write run (rc=$rc): $out"
G=$(newrun colg); taskblock "$G"
out=$(./bin/crown local collect "$G" 2>&1); rc=$?
[ $rc != 0 ] && grep -q 'no captured response' <<<"$out" && ok "collect refuses a run with no captured response" || no "refuse no capture (rc=$rc): $out"
./bin/crown local collect "$A" >/dev/null 2>&1 && no "an already-collected run collected again" || ok "collect refuses an already-collected run"

# legacy behavior for member-written records is unchanged (no collection block, no strict path)
mkdir "$T/l1" && printf '# run\n\n## Findings\n\nnone\n' > "$T/l1/report.md"
out=$(python3 lib/review_check.py "$T/l1" 2>&1); rc=$?
[ $rc = 0 ] && grep -q 'OK report-only run' <<<"$out" && ok "legacy: a member report with a Findings section still passes as before" || no "legacy report (rc=$rc): $out"
mkdir "$T/l2" && printf '{"status":"BLOCKED","commits":[],"blocked_reason":"x"}' > "$T/l2/manifest.json"
out=$(python3 lib/review_check.py "$T/l2" 2>&1); rc=$?
[ $rc = 0 ] && grep -q 'OK no commits' <<<"$out" && ok "legacy: a member BLOCKED manifest still passes as before" || no "legacy manifest (rc=$rc): $out"
cp -r "$A/out" "$T/l3" && jq 'del(.collection)' "$A/out/manifest.json" > "$T/l3/manifest.json"
python3 lib/review_check.py "$T/l3" >/dev/null 2>&1 && ok "legacy: the same files without a collection block take the legacy path, not the strict one" || no "legacy path selection"

[ $fail = 0 ] && echo "test_collect: all ok" || echo "test_collect: FAILURES"
exit $fail
