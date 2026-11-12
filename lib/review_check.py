#!/usr/bin/env python3
"""Checks that an agent's output is a series of change-specific patches with their context,
not one monolithic patch. Usage: review_check.py OUT [--allow-empty]   (exit 1 on any FAIL, 2 on a usage error)
OUT is the member's output directory (RUN/out; given RUN, whose out directory exists, it checks RUN/out): it holds manifest.json and the patches in OUT/patches/*.patch, the one place `review apply` reads them from.
A review run has no patches: report.md (or PREFIXreport.md) with a Findings heading is its deliverable."""
import glob, json, os, re, sys
from email.utils import parsedate_to_datetime

args = [a for a in sys.argv[1:] if not a.startswith("--")]
unknown = [a for a in sys.argv[1:] if a.startswith("--") and a != "--allow-empty"]
if unknown or len(args) > 1:
    print("crown: %s\nusage: review_check.py OUT [--allow-empty]" % ("unknown option " + unknown[0] if unknown else "one OUT directory, not %d" % len(args)), file=sys.stderr)
    sys.exit(2)
allow_empty = "--allow-empty" in sys.argv   # a team member may return no commits (blocked, or nothing to change)
run = args[0] if args else "."
fails, warns, notes = [], [], []
F = lambda m: fails.append("FAIL " + m)
W = lambda m: warns.append("WARN " + m)
N = lambda m: notes.append("NOTE " + m)
# a run directory (RUN_DIR) was given where OUT (RUN_DIR/out) is meant: use its out directory, unless the directory is an OUT itself
if os.path.isdir(os.path.join(run, "out")) and not os.path.isdir(os.path.join(run, "patches")) and not os.path.exists(os.path.join(run, "manifest.json")):
    run = os.path.join(run, "out")
    N("checked %s (a run directory was given; the output directory is RUN_DIR/out)" % run)

# a collected read-only record (a manifest carrying a "collection" block, written by
# `crown local collect`) is gated on a strict path, not by the shortcuts below: the report
# and the manifest are validated as a pair, the preserved response's hash is recomputed
# against the capture hash recorded at collection, every provenance grade is enforced (a
# crown-verified grade must resolve to the Crown check that backs it), and the status
# gates: INCOMPLETE never passes, BLOCKED passes only on the member's own stated
# blockage, DONE only on a complete sourced record whose DONE passed. A member-written
# record carries no collection block and keeps the behavior below, unchanged.
_cman = None
try:
    _cman = json.load(open(os.path.join(run, "manifest.json")))
except Exception:
    _cman = None
if isinstance(_cman, dict) and isinstance(_cman.get("collection"), dict):
    import hashlib
    man, col = _cman, _cman["collection"]
    cfails = []
    CF = lambda m: cfails.append("FAIL " + m)
    reps = sorted(glob.glob(os.path.join(run, "*report.md")))
    rep_text = ""
    if not reps:
        CF("collected record: no report.md beside its manifest (a collected record is validated as a pair)")
    else:
        rep_text = open(reps[0], errors="replace").read()
        if "## Member response (verbatim, collected)" not in rep_text:
            CF("collected record: %s does not carry the member's response under the marked section '## Member response (verbatim, collected)'" % os.path.basename(reps[0]))
    if not col.get("collected_by"): CF("collection block: collected_by is missing")
    if not col.get("collected_at"): CF("collection block: collected_at is missing")
    src = col.get("source") if isinstance(col.get("source"), dict) else {}
    if src.get("kind") not in ("transcript", "session"): CF("collection block: source.kind is %r, not transcript or session" % src.get("kind"))
    if not src.get("run"): CF("collection block: source.run is missing (the capture must be bound to its run)")
    sha = src.get("sha256") or ""
    if not re.fullmatch(r"[0-9a-f]{64}", sha): CF("collection block: source.sha256 is not a SHA-256 hash")
    ref = src.get("ref") or ""
    raw_text = None
    if not ref or "/" in ref or ref in (".", ".."):
        CF("collection block: source.ref %r is not a plain file name in OUT" % ref)
    elif not os.path.isfile(os.path.join(run, ref)):
        CF("collected record: the preserved raw response %s is not in OUT" % ref)
    else:
        rawb = open(os.path.join(run, ref), "rb").read()
        if re.fullmatch(r"[0-9a-f]{64}", sha) and hashlib.sha256(rawb).hexdigest() != sha:
            CF("collected record: the preserved raw response's SHA-256 does not match the capture hash recorded in the manifest (the evidence was altered after collection)")
        raw_text = rawb.decode("utf-8", "replace")
    if reps and re.fullmatch(r"[0-9a-f]{64}", sha) and sha not in rep_text:
        CF("collected record: report.md does not state the capture hash, so the report and the preserved response are not linked")
    prov = col.get("provenance")
    grades = {}
    if not isinstance(prov, dict):
        CF("collection block: provenance is missing (a collected record grades every value)")
    else:
        for key in ("status", "task", "commits", "artifacts", "deviations"):
            if key not in prov: CF("provenance does not grade %r" % key)
        for key, g in prov.items():
            if isinstance(g, str) and g in ("member-stated", "crown-observed", "unknown"):
                grades[key] = g
            elif isinstance(g, dict) and g.get("grade") == "crown-verified":
                grades[key] = "crown-verified"
                cref = g.get("ref") or ""
                fname, _, cname = cref.partition("#")
                if not g.get("check") or not cname or "/" in fname or not os.path.isfile(os.path.join(run, fname)):
                    CF("provenance: %r is graded crown-verified but its check reference %r does not resolve to a record in OUT" % (key, cref))
                else:
                    try:
                        ev = json.load(open(os.path.join(run, fname)))
                        entry = next((c for c in ev.get("checks", []) if c.get("name") == cname), None)
                    except Exception:
                        entry = None
                    if entry is None:
                        CF("provenance: %r is graded crown-verified but %s holds no check named %r" % (key, fname, cname))
                    elif key == "done":
                        d = man.get("done") if isinstance(man.get("done"), dict) else {}
                        if entry.get("exit_code") != d.get("exit_code"):
                            CF("provenance: the DONE check recorded in %s exited %r, not the manifest's %r" % (fname, entry.get("exit_code"), d.get("exit_code")))
            else:
                CF("provenance: %r carries an unrecognized grade %r" % (key, g))
    if man.get("commits") != []:
        CF("collected record: commits is not [] (a collected record is a read-only run's; it carries no commits)")
    st = man.get("status")
    if st not in ("DONE", "BLOCKED", "INCOMPLETE"):
        CF("collected record: status %r is not DONE, BLOCKED or INCOMPLETE" % st)
    elif st == "INCOMPLETE":
        CF("collected record is INCOMPLETE: the response did not establish the full contract record (an INCOMPLETE record never passes, even when a check inside it succeeded)")
    elif st == "BLOCKED":
        br = man.get("blocked_reason")
        if not isinstance(br, str) or not br.strip():
            CF("collected record: status BLOCKED carries no blocked_reason")
        else:
            if grades.get("blocked_reason") != "member-stated":
                CF("collected record: blocked_reason is graded %r, not member-stated (a blockage the member did not state cannot be collected as one)" % grades.get("blocked_reason"))
            norm = lambda s: re.sub(r"\s+", " ", s).strip()
            if raw_text is not None and norm(br) not in norm(raw_text):
                CF("collected record: blocked_reason does not appear in the member's preserved response")
    elif st == "DONE":
        d = man.get("done") if isinstance(man.get("done"), dict) else {}
        if d.get("exit_code") != 0:
            CF("collected record: status DONE but done is missing or its exit code is not 0 (a passed DONE verifies that command's result, and a DONE record stands on it)")
        for key in ("status", "task", "commits", "artifacts", "deviations", "touched_paths"):
            if grades.get(key) == "unknown":
                CF("collected record: status DONE but %r is graded unknown" % key)
        if "touched_paths" not in man:
            CF("collected record: status DONE but the manifest carries no touched_paths")
    arts = man.get("artifacts") if isinstance(man.get("artifacts"), list) else []
    apaths = {a.get("path") for a in arts if isinstance(a, dict)}
    if not any(isinstance(a, dict) and a.get("kind") == "report" for a in arts):
        CF("collected record: artifacts lists no report")
    if ref and ref not in apaths:
        CF("collected record: artifacts does not list the preserved raw response %r" % ref)
    for line in cfails:
        print(line)
    if cfails:
        print("%d fail, 0 warn" % len(cfails)); sys.exit(1)
    print("OK collected read-only run: status %s (pair validated, source hash verified, provenance enforced)" % st)
    sys.exit(0)

patches = sorted(glob.glob(os.path.join(run, "patches", "*.patch")))
if not patches:
    # a review run returns a report, not patches
    # the report is report.md, or PREFIXreport.md when the task block gave an OUT_PREFIX (a team run: review--report.md)
    for rep in sorted(glob.glob(os.path.join(run, "*report.md"))):
        text = open(rep, errors="replace").read()
        if text.strip() and re.search(r"(?mi)^#+\s*findings\b", text):
            print("OK report-only run: %s holds a Findings section (%d chars)" % (os.path.basename(rep), len(text))); sys.exit(0)
    try:
        m0 = json.load(open(os.path.join(run, "manifest.json")))
    except Exception:
        m0 = None
    if m0 is not None and m0.get("commits") == [] and (allow_empty or m0.get("status") == "BLOCKED"):
        print("OK no commits (status %s)%s" % (m0.get("status"), ": " + m0["blocked_reason"] if m0.get("blocked_reason") else "")); sys.exit(0)
    print("FAIL no patches found in %s, and no report.md (or PREFIXreport.md) with a Findings section" % run); sys.exit(1)
try:
    man = json.load(open(os.path.join(run, "manifest.json")))
except Exception as e:
    man = {}; F("manifest.json missing or unreadable (%s)" % e)

info = []
for p in patches:
    t = open(p, errors="replace").read()
    unfolded = re.sub(r"\n[ \t]+", " ", t.split("\n\n", 1)[0])   # git folds long header lines
    subj = re.search(r"(?m)^Subject: (?:\[PATCH[^\]]*\] )?(.*)$", unfolded)
    date = re.search(r"(?m)^Date: (.*)$", t)
    head, _, rest = t.partition("\n---\n")
    body = head.split("\n\n", 1)[1].strip() if "\n\n" in head else ""
    files = re.findall(r"(?m)^diff --git a/(\S+) b/", t)
    changed = len(re.findall(r"(?m)^[+-](?![+-]{2} )", t))
    areas = {f.split("/")[0] for f in files}
    ts = None
    if date:
        try: ts = parsedate_to_datetime(date.group(1)).timestamp()
        except Exception: pass
    info.append({"name": os.path.basename(p), "subject": subj.group(1).strip() if subj else "", "body": body,
                 "files": files, "changed": changed, "areas": areas, "ts": ts})

n = len(info)
nums = [re.match(r"(\d{4})-", i["name"]) for i in info]
if not all(nums) or [int(m.group(1)) for m in nums] != list(range(1, n + 1)):
    F("patches are not numbered 0001..%04d in order (git format-patch output)" % n)
for i in info:
    if not i["subject"]: F("%s: no subject" % i["name"])
    if not i["body"]:
        F("%s: the commit message has no body; each commit must say what changed and why, so its context travels with it" % i["name"])
if man:
    commits = man.get("commits", [])
    if len(commits) != n: F("manifest lists %d commit(s) but there are %d patch(es): one patch per commit" % (len(commits), n))
    subjects = {c.get("subject", "").strip() for c in commits}
    for i in info:
        if subjects and i["subject"] not in subjects: W("%s: its subject is not among the manifest's commits" % i["name"])
    adv = man.get("commit_advice")
    if not adv: W("manifest has no commit_advice")
    elif len(adv) != n: W("commit_advice has %d entries for %d patches" % (len(adv), n))
    groups = man.get("patch_groups")
    if not groups: W("manifest has no patch_groups (which commits belong to which change)")
    else:
        listed = [s for g in groups for s in g.get("commits", [])]
        if sorted(listed) != sorted(c.get("sha", "")[:7] for c in commits) and sorted(listed) != sorted(c.get("sha", "") for c in commits) \
           and sorted(listed) != sorted(c.get("subject", "") for c in commits):
            W("patch_groups do not cover every commit exactly once (list commits by sha or subject)")
        for g in groups:
            if not g.get("why"): W("patch group %r has no why" % g.get("name"))
if not os.path.exists(os.path.join(run, "series.md")) and not os.path.exists(os.path.join(run, "patches", "series.md")):
    W("no series.md (a short account of each patch in order)")

# monolith heuristics
total = sum(i["changed"] for i in info) or 1
allareas = set().union(*[i["areas"] for i in info])
if n == 1 and len(allareas) >= 3:
    F("one patch touches %d areas (%s): this looks monolithic; split it into change-specific commits" % (len(allareas), ", ".join(sorted(allareas))))
if n > 1:
    big = max(info, key=lambda i: i["changed"])
    if big["changed"] / total > 0.7 and len(big["areas"]) >= 3:
        W("%s holds %d%% of the changed lines across %d areas: check it is one change, not several combined" % (big["name"], 100 * big["changed"] // total, len(big["areas"])))
ts = [i["ts"] for i in info if i["ts"]]
if n >= 3 and len(ts) == n and max(ts) - min(ts) < 120:
    N("all %d commits are dated within %d seconds: they may have been made in one batch at the end; make sure each one really stands alone and its message records the reasoning at that step" % (n, int(max(ts) - min(ts))))

for i in info:
    print("%s  %s  (%d file(s), %d changed line(s))" % (i["name"], i["subject"][:70], len(i["files"]), i["changed"]))
out = fails + warns + notes
print("\n".join(out) if out else "series ok: %d change-specific patch(es), each with its own message" % n)
print("%d fail, %d warn" % (len(fails), len(warns)))
sys.exit(1 if fails else 0)
