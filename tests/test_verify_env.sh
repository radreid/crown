#!/usr/bin/env bash
# `crown feature verify` and `crown release verify` run the test command without the project's cloud binding in the
# environment. Run: tests/test_verify_env.sh
set -u
cd "$(dirname "$0")/.." || exit 1
# shellcheck source=hermetic.sh
. tests/hermetic.sh
T=$(mktemp -d); fail=0; DA=$PWD/bin/crown
ok() { echo "ok   $1"; }; no() { echo "FAIL $1"; fail=1; }
export HOME=$T/home CROWN_CONF=$T/c CROWN_STATE=$T/s GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@example.net GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@example.net
export CROWN_PROJECT=app
mkdir -p "$HOME" "$T/c/projects"
R=$T/app; git init -q -b master "$R"; echo 0.1.0 > "$R/VERSION"
git -C "$R" add -A && git -C "$R" commit -q -m one && git -C "$R" branch develop && git -C "$R" branch feature/f
jq -n --arg p "$R" --arg c "env > $T/env.out" '{schema:1, project:"app", methodology:"gitflow", repo:{url:"https://github.com/acme/app", path:$p, long_lived:["master","develop"]}, test_command:$c}' > "$T/c/projects/app.json"
bound() { ANTHROPIC_PROFILE=p CROWN_CLOUD_WORKSPACE=wrkspc_x CROWN_CLOUD_PROJECT=app "$@"; }
check() { # label
  if [ -f "$T/env.out" ] && ! grep -Eq '^(ANTHROPIC_PROFILE|CROWN_CLOUD_WORKSPACE|CROWN_CLOUD_PROJECT)=' "$T/env.out"; then ok "$1: the suite runs without the cloud binding"; else no "$1: binding visible: $(grep -E '^(ANTHROPIC|CROWN_CLOUD)' "$T/env.out" 2>&1)"; fi
  rm -f "$T/env.out"
}
bound "$DA" feature verify f >/dev/null 2>&1; check "feature verify"
bound "$DA" release verify 0.2.0 >/dev/null 2>&1; check "release verify"
rm -rf "$T"; exit $fail
