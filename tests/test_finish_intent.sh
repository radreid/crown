#!/usr/bin/env bash
# The finish-intent record of the finishing verbs (feature finish, release finish): what a rerun does with the record of a finish that
# was cut off. Written from the SPEC of the record (gitflow.sh, intent_*), not from its code: the fixtures are record states, made by
# hand — a record whose refs origin holds at the new values (the push happened), at the old values (it never did), a mix, an origin
# that cannot be asked, a live lock, a stale lock, and no flock. Fixtures and conventions follow tests/test_marshal_flow.sh.
# Run: tests/test_finish_intent.sh
set -u
cd "$(dirname "$0")/.." || exit 1
# shellcheck source=hermetic.sh
. tests/hermetic.sh
T=$(mktemp -d); fail=0; DA=$PWD/bin/crown; TOOL=$PWD
trap 'jobs -p | xargs -r kill 2>/dev/null; rm -rf "$T" "$HERMETIC"' EXIT
ok() { echo "ok   $1"; }; no() { echo "FAIL $1"; fail=1; }
export HOME=$T/home CROWN_CONF=$T/c CROWN_STATE=$T/s CROWN_RUN_TMP=$T/shm GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@example.net GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@example.net
export CROWN_PROJECT=app
S=$CROWN_STATE
mkdir -p "$HOME" "$T/c/projects" "$T/bin" "$T/shm" "$T/scratch"
cat > "$T/bin/gh" <<G
#!/usr/bin/env bash
echo "\$*" >> "$T/gh.log"
case "\$*" in *"pr checks"*) true;; *"pr create"*) echo https://example.net/acme/app/pull/1;; esac
G
chmod +x "$T/bin/gh"; export PATH=$T/bin:$PATH
R=$T/app; git init -q -b master "$R"; git init -q --bare "$T/origin.git"
echo 0.1.0 > "$R/VERSION"; printf '# Changelog\n\n## [Unreleased]\n\n- a change\n' > "$R/CHANGELOG.md"
git -C "$R" add -A && git -C "$R" commit -q -m one && git -C "$R" branch develop && git -C "$R" remote add origin "$T/origin.git" && git -C "$R" push -q origin master develop
git -C "$R" checkout -q -b parked
jq -n --arg p "$R" '{schema:1, project:"app", methodology:"gitflow", repo:{url:"https://github.com/acme/app", path:$p, long_lived:["master","develop"]}, test_command:"true"}' > "$T/c/projects/app.json"
F="$DA feature"; REL="$DA release"
out() { cat "$T/o" "$T/e"; }
run() { "$@" >"$T/o" 2>"$T/e"; }             # run CMD...: stdout and stderr in $T/o and $T/e, the status returned
tip() { git -C "$R" rev-parse "$1"; }
otip() { git --git-dir="$T/origin.git" rev-parse "$1"; }
irec() { echo "$S/finish-intent/app-$1.json"; }   # the record file of a key (feature-NAME or release-VERSION)
commit_on() { # BRANCH FILE: one commit on BRANCH (in a temporary worktree)
  local w; w=$(mktemp -d "$T/w.XXXXXX"); git -C "$R" worktree add -q "$w" "$1"
  echo "$1" > "$w/$2"; git -C "$w" add -A; git -C "$w" commit -q -m "$1 $2"; git -C "$R" worktree remove --force "$w"
}
mkfeat() { # NAME: a started, committed, verified feature
  run $F start "$1" || return 1
  commit_on "feature/$1" "$1.txt"
  run $F verify "$1" >/dev/null 2>&1
}
merge_of() { # FEATURE: print a merge commit of feature/FEATURE into develop, made in a temporary worktree on a detached head (develop itself is not moved)
  local w; w=$(mktemp -d "$T/w.XXXXXX"); git -C "$R" worktree add -q --detach "$w" develop
  git -C "$w" merge -q --no-ff "feature/$1" -m "Merge branch 'feature/$1' into develop"
  git -C "$w" rev-parse HEAD
  git -C "$R" worktree remove --force "$w"
}
frecord() { # NAME MERGED DONE: write the record of a feature finish whose push reached origin (develop was at $2's parent state before)
  local d0; d0=$(tip develop)
  mkdir -p "$S/finish-intent"
  jq -nc --arg name "$1" --arg d0 "$d0" --arg m "$2" --arg h "$(tip "feature/$1")" --argjson done "$3" \
    '{schema:1, verb:"feature:finish", project:"app", name:$name, pushed:true,
      refs:[{ref:"refs/heads/develop", local_old:$d0, origin_old:$d0, new:$m}],
      ctx:{head:$h, keep:"", pushd:"1", pushwhy:"", rdel:"", k:("feature-" + $name + "-into-develop")}, done:$done}' > "$(irec "feature-$1")"
}
tokof() { sed -n 's/^plan token: \([0-9a-f]*\).*/\1/p' "$T/o"; }

# ============================================================ a record at the new values: the rerun completes only what is left
mkfeat f1
M1=$(merge_of f1); git -C "$R" push -q origin "$M1:refs/heads/develop"   # the push happened; the local steps did not
frecord f1 "$M1" '["journal"]'
d0=$(tip develop)
run $F finish f1; rc=$?
[ $rc = 0 ] && grep -q "was cut off" "$T/o" && grep -q "steps already done: journal" "$T/o" && [ -f "$(irec feature-f1)" ] && [ "$(tip develop)" = "$d0" ] \
  && ok "resume: the plan of a cut-off finish says what is left and changes nothing (the record stays)" || no "SPEC resume plan (rc=$rc): $(out)"
t=$(tokof)
run $F finish f1 --plan "$t" --approved go; rc=$?
[ $rc = 0 ] && [ "$(tip develop)" = "$M1" ] && ! git -C "$R" rev-parse -q --verify "feature/f1" >/dev/null 2>&1 && [ ! -f "$(irec feature-f1)" ] \
  && ok "resume: the apply moves develop, deletes the branch and removes the record" || no "SPEC resume apply (rc=$rc): $(out)"

# ============================================================ a record at the old values: a plan drops nothing; the apply drops it and starts over
mkfeat f2
M2=$(merge_of f2)   # made locally only: the push never happened
frecord f2 "$M2" '[]'
d0=$(tip develop)
run $F finish f2; rc=$?
[ $rc = 0 ] && grep -q "stopped before anything reached origin" "$T/e" && [ -f "$(irec feature-f2)" ] && [ "$(tip develop)" = "$d0" ] \
  && ok "stale: the plan of a finish whose push never happened drops nothing (the record stays)" || no "SPEC stale plan (rc=$rc): $(out)"
t=$(tokof)
run $F finish f2 --plan "$t" --approved go; rc=$?
[ $rc = 0 ] && [ ! -f "$(irec feature-f2)" ] && [ "$(tip develop)" != "$d0" ] && [ "$(otip develop)" = "$(tip develop)" ] && ! git -C "$R" rev-parse -q --verify "feature/f2" >/dev/null 2>&1 \
  && ok "stale: the apply removes the record and the finish runs from the start" || no "SPEC stale apply (rc=$rc): $(out)"

# ============================================================ a rejected push keeps the record (and says origin may hold the merge)
mkfeat f3
printf '#!/bin/sh\necho rejected >&2\nexit 1\n' > "$T/origin.git/hooks/pre-receive"; chmod +x "$T/origin.git/hooks/pre-receive"
d0=$(tip develop)
run $F finish f3; t=$(tokof)
run $F finish f3 --plan "$t" --approved go; rc=$?
[ $rc != 0 ] && grep -q "origin may hold the merge anyway" "$T/e" && [ -f "$(irec feature-f3)" ] && [ "$(tip develop)" = "$d0" ] \
  && ok "push failure: the finish refuses, keeps the record, and moves nothing locally" || no "SPEC push failure (rc=$rc): $(out)"
rm -f "$T/origin.git/hooks/pre-receive"
run $F finish f3; t=$(tokof)
run $F finish f3 --plan "$t" --approved go; rc=$?
[ $rc = 0 ] && [ ! -f "$(irec feature-f3)" ] && [ "$(otip develop)" = "$(tip develop)" ] \
  && ok "push failure: the rerun asks origin, drops the stale record and finishes" || no "SPEC push failure rerun (rc=$rc): $(out)"

# ============================================================ a pushed record whose origin cannot be asked: refused, nothing changes
mkfeat f4
M4=$(merge_of f4); git -C "$R" push -q origin "$M4:refs/heads/develop"
frecord f4 "$M4" '[]'
d0=$(tip develop)
mv "$T/origin.git" "$T/origin.dead"
run $F finish f4; rc=$?
mv "$T/origin.dead" "$T/origin.git"
[ $rc != 0 ] && grep -q "origin could not be asked" "$T/e" && [ -f "$(irec feature-f4)" ] && [ "$(tip develop)" = "$d0" ] \
  && ok "unreachable: a pushed record whose origin cannot be asked is refused, the record stays" || no "SPEC unreachable probe (rc=$rc): $(out)"
rm -f "$(irec feature-f4)"
git -C "$R" update-ref refs/heads/develop "$(otip develop)"   # the f4 fixture left origin's develop ahead of the local one: resync for the tests below

# ============================================================ mixed refs on a release record: refused, each difference named
m0=$(tip master); dv=$(tip develop); odv=$(otip develop)
w=$(mktemp -d "$T/w.XXXXXX"); git -C "$R" worktree add -q --detach "$w" master; echo x > "$w/x.txt"; git -C "$w" add -A; git -C "$w" commit -q -m x; NM=$(git -C "$w" rev-parse HEAD); git -C "$R" worktree remove --force "$w"
git -C "$R" push -q origin "$NM:refs/heads/master"   # origin's master moved; develop and the tag did not
mkdir -p "$S/finish-intent"
jq -nc --arg m0 "$m0" --arg nm "$NM" --arg dv "$dv" --arg odv "$odv" \
  '{schema:1, verb:"release:finish", project:"app", name:"9.9.9", pushed:true,
    refs:[{ref:"refs/heads/master", local_old:$m0, origin_old:$m0, new:$nm},
          {ref:"refs/heads/develop", local_old:$dv, origin_old:$odv, new:$nm},
          {ref:"refs/tags/9.9.9", local_old:"", origin_old:"", new:"", commit:$nm}],
    ctx:{branch:"release/9.9.9", head:$dv, second:"develop", keep:"", ignored:"", ignore_checks:"", rb0:"", k1:"release-9.9.9-into-master", k2:"release-9.9.9-into-develop"}, done:[]}' > "$(irec release-9.9.9)"
run $REL finish 9.9.9; rc=$?
[ $rc != 0 ] && grep -q "some of its refs but not all" "$T/e" && [ -f "$(irec release-9.9.9)" ] && [ "$(tip master)" = "$m0" ] && [ "$(tip develop)" = "$dv" ] \
  && ok "mixed: a record whose refs origin holds only in part is refused, nothing moved" || no "SPEC mixed probe (rc=$rc): $(out)"
rm -f "$(irec release-9.9.9)"
git --git-dir="$T/origin.git" update-ref refs/heads/master "$m0"   # put origin's master back for the tests below

# ============================================================ the lock: a live holder refuses; a dead one is taken over
mkfeat f5
mkdir -p "$(irec feature-f5).run"
sleep 30 & SLP=$!
tok5=$(awk '{print $22}' "/proc/$SLP/stat")
echo "$SLP $tok5" > "$(irec feature-f5).run/pid"
run $F finish f5; rc=$?
kill "$SLP" 2>/dev/null; wait "$SLP" 2>/dev/null
[ $rc != 0 ] && grep -q "another finish of feature-f5 is running" "$T/e" \
  && ok "lock: a finish whose lock a live process holds is refused" || no "SPEC live lock (rc=$rc): $(out)"
run $F finish f5; rc=$?
[ $rc = 0 ] && [ ! -d "$(irec feature-f5).run" ] \
  && ok "lock: a dead holder's lock is taken over, and removed when the verb ends" || no "SPEC stale lock (rc=$rc): $(out)"

# ============================================================ no flock: the record is not written and the verb says so
mkdir -p "$T/shim"
for x in mkdir chmod mv cat rm dirname basename git jq python3 date stat find awk sed grep tr head tail sort mktemp readlink ls bash sh env uname id hostname; do ln -s "$(command -v "$x")" "$T/shim/$x" 2>/dev/null; done
ln -sf /bin/bash "$T/shim/bash"; ln -sf /bin/bash "$T/shim/sh"
cat > "$T/noflock.sh" <<EOS
export HOME=$T/home CROWN_CONF=$T/c CROWN_STATE=$T/s CROWN_PROJECT=app PROJ=app
. $TOOL/lib/lib.sh
. $TOOL/lib/gitflow.sh
intent_write probe-key '{"schema":1}'
echo WROTE
EOS
PATH=$T/shim bash "$T/noflock.sh" >"$T/o" 2>"$T/e"; rc=$?
[ $rc != 0 ] && grep -q "the flock command (util-linux) is not installed" "$T/e" && [ ! -f "$(irec probe-key)" ] \
  && ok "no flock: the intent record is not written and the refusal says why" || no "SPEC no flock (rc=$rc): $(out)"

[ "$fail" = 0 ] && echo "finish intent: all passed" || echo "finish intent: FAILED"
exit "$fail"
