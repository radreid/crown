#!/usr/bin/env python3
"""Collect a read-only run whose member returned its result as a response but wrote no
report pair into OUT (the read-only counterpart of the harvest): build the run's standard
record from the member's captured response, as the lead, outside the member's sandbox.
Usage: collect.py RUN_DIR   (invoked by `crown local collect`; the caller has already
established that the run's class is read-only)

The member's captured response is the only member-side input, and it is preserved
byte-exact as its own artifact in OUT: OUT/transcript for a command runtime (the dispatch
already captured it there), or a response the dispatching session deposited at
RUN/response for an in-session runtime, copied here to OUT/response. Extraction is
deterministic pattern matching against the contract's final-report format
(contract/contract.md): a value the patterns cannot source is recorded unknown, never
inferred, and a response that cannot support a complete record collects as INCOMPLETE.
The manifest is the collector's, and says so in deviations[]: every value carries a
provenance grade (member-stated / crown-observed / crown-verified / unknown), a
crown-verified grade points at the Crown check that backs it in
collection-evidence.json, and `done` is Crown's own re-execution of the task's DONE
when the task names one. Collection is a fallback for ABSENT member output only: a
member-written report or manifest in OUT refuses the collect, untouched.
`crown review check` gates a collected record on its strict path, exactly as it gates
any other; INCOMPLETE never passes it."""
import hashlib, json, os, re, subprocess, sys
from datetime import datetime, timezone

def main():
    RUN = os.path.abspath(sys.argv[1])
    CLONE, OUT = os.path.join(RUN, "clone"), os.path.join(RUN, "out")
    TASKF = os.path.join(RUN, "task.md")

    def die(msg):
        print("crown: collect: %s" % msg, file=sys.stderr); sys.exit(2)

    if not (os.path.isfile(os.path.join(RUN, "refs.before")) and os.path.isfile(TASKF)):
        die("%s is not a run directory made by prepare" % RUN)
    os.makedirs(OUT, exist_ok=True)

    # collection is a fallback for absent output: any member-written pair (or half of one)
    # refuses it, preserved exactly as supplied
    for p in sorted(os.listdir(OUT)):
        if p.endswith("report.md"):
            die("%s already holds a member-written %s: collection is a fallback for absent output, and member files are never replaced" % (OUT, p))
    mpath = os.path.join(OUT, "manifest.json")
    if os.path.exists(mpath):
        try:
            m0 = json.load(open(mpath))
        except Exception:
            m0 = None
        if isinstance(m0, dict) and isinstance(m0.get("collection"), dict):
            die("%s is already collected: its manifest carries a collection block" % OUT)
        die("%s already holds a member-written manifest.json: collection is a fallback for absent output, and member files are never replaced" % OUT)

    # the task block (the lead's lines in RUN/task.md, the same source harvest reads)
    task_txt = open(TASKF, errors="replace").read()
    def task_line(name):
        m = re.search(r"(?m)^%s:[ \t]*(.*)$" % name, task_txt)
        return m.group(1).strip() if m else ""
    TASK = task_line("TASK")
    DONE_CMD = task_line("DONE")
    BASE = task_line("BASE")
    m = re.search(r"(?m)^BASE_SHA=(\S+)$", task_txt)
    BASE_SHA = m.group(1) if m else ""

    # the captured response: the dispatch's own capture, or the session's deposit
    src_kind = src_ref = None
    raw = None
    deposit_meta = {}
    tpath = os.path.join(OUT, "transcript")
    dpath = os.path.join(RUN, "response")
    if os.path.isfile(tpath):
        src_kind, src_ref = "transcript", "transcript"
        raw = open(tpath, "rb").read()
    elif os.path.isfile(dpath):
        src_kind, src_ref = "session", "response"
        raw = open(dpath, "rb").read()
        with open(os.path.join(OUT, "response"), "wb") as f:
            f.write(raw)
        spath = os.path.join(RUN, "response.source.json")
        if os.path.isfile(spath):
            try:
                deposit_meta = json.load(open(spath))
            except Exception:
                deposit_meta = {}
    else:
        die("no captured response for this run: neither OUT/transcript (a command runtime's capture) "
            "nor RUN/response (an in-session runtime's deposit) exists, and without a capture there is no collection")
    sha = hashlib.sha256(raw).hexdigest()
    text = raw.decode("utf-8", "replace")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # environment, crown-observed from the dispatch record or the deposit's source record
    env, env_grade = {}, "unknown"
    dj = os.path.join(OUT, "dispatch.json")
    if os.path.isfile(dj):
        try:
            d = json.load(open(dj))
            for k in ("runtime", "model"):
                if d.get(k):
                    env[k] = d[k]
            env_grade = "crown-observed"
        except Exception:
            pass
    if not env and deposit_meta:
        for k in ("runtime", "model"):
            if deposit_meta.get(k):
                env[k] = deposit_meta[k]
        if env:
            env_grade = "crown-observed"

    # deterministic extraction from the response, in the contract's final-report format
    lines = text.splitlines()
    first = next((l for l in lines if l.strip()), "")
    claim, reason = None, ""
    mm = re.match(r"^(DONE|BLOCKED)\b[:\-—]?\s*(.*)$", first.strip())
    if mm:
        claim, reason = mm.group(1), mm.group(2).strip()
    if claim == "BLOCKED" and not reason:
        rm = re.search(r"(?mi)^\s*(?:blocked_reason|blocked reason|reason)\s*:\s*(.+)$", text)
        if rm:
            reason = rm.group(1).strip()

    def labeled(label):
        lm = re.search(r"(?mi)^%s\s*:\s*(.*)$" % re.escape(label), text)
        return lm.group(1).strip() if lm else None

    def as_list(v):
        # "none"/"nothing" -> []; a comma list of spaceless entries -> the list; else unsourced
        if v is None:
            return None
        if v.rstrip(".").lower() in ("", "none", "nothing"):
            return []
        parts = [p.strip() for p in v.split(",")]
        return parts if all(parts) and not any(" " in p for p in parts) else None

    files_stated = as_list(labeled("Files changed"))
    noticed = as_list(labeled("Noticed, not acted on"))
    member_dev = labeled("Deviations")
    member_dev = [] if member_dev is None or member_dev.rstrip(".").lower() in ("", "none") else [member_dev]

    # Crown's own checks: the DONE re-execution and the clone's state (collection-evidence.json)
    checks = []
    done, done_grade = None, "unknown"
    if DONE_CMD:
        p = subprocess.run(["bash", "-c", DONE_CMD], cwd=CLONE, capture_output=True, text=True)
        tail = "\n".join(((p.stdout + p.stderr).strip().splitlines() or [""])[-3:])
        done = {"command": DONE_CMD, "exit_code": p.returncode, "output_tail": tail}
        done_grade = {"grade": "crown-verified", "check": "the task's DONE, re-executed by the collector in the clone",
                      "ref": "collection-evidence.json#done"}
        checks.append({"name": "done", "kind": "command-re-run", "command": DONE_CMD, "cwd": "clone",
                       "exit_code": p.returncode, "output_tail": tail, "at": now})
    else:
        dm = re.search(r"(?mi)^done check\s*:\s*(.+)$", text)
        if dm and re.search(r"exit (?:code )?0\b", dm.group(1)):
            done = {"command": "", "exit_code": 0, "output_tail": dm.group(1).strip()}
            done_grade = "member-stated"

    def git(*a):
        return subprocess.run(["git", "-C", CLONE] + list(a), capture_output=True, text=True).stdout.strip()

    if not BASE_SHA and BASE:
        # the base commit the way harvest finds it: the merge-base of the clone's HEAD and the base branch
        for ref in ("refs/remotes/origin/" + BASE, "refs/heads/" + BASE):
            p = subprocess.run(["git", "-C", CLONE, "merge-base", "HEAD", ref], capture_output=True, text=True)
            if p.returncode == 0 and p.stdout.strip():
                BASE_SHA = p.stdout.strip()
                break

    porc = git("status", "--porcelain")
    tree_paths = [l[3:] for l in porc.splitlines() if len(l) > 3] if porc else []
    past = None
    if BASE_SHA:
        n = git("rev-list", "--count", "%s..HEAD" % BASE_SHA)
        past = int(n) if n.isdigit() else None
    checks.append({"name": "clone-state", "kind": "clone-inspection",
                   "commits_past_base": past, "working_tree_paths": tree_paths, "at": now})
    with open(os.path.join(OUT, "collection-evidence.json"), "w") as f:
        json.dump({"collected_at": now, "checks": checks}, f, indent=2)
        f.write("\n")

    # the determination: a stated outcome the evidence can carry, or INCOMPLETE with the gaps named
    missing = []
    if claim is None:
        missing.append("the response states no DONE or BLOCKED outcome in the contract's format")
    if claim == "BLOCKED" and not reason:
        missing.append("the response claims BLOCKED but no blocked_reason could be extracted from it")
    if claim == "DONE":
        if done is None:
            missing.append("the DONE check could not be sourced (no DONE named in the task, none stated with an exit status)")
        elif done["exit_code"] != 0:
            missing.append("the DONE check did not pass (exit %s)" % done["exit_code"])
        if files_stated is None:
            missing.append("the files the member changed could not be extracted from the response")
        if past is None:
            missing.append("the clone's commits past the base could not be counted (no BASE_SHA in the task block)")
        elif past > 0:
            missing.append("the clone holds %d commit(s) past the base; a read-only run makes none" % past)
    if claim == "BLOCKED" and not missing:
        status = "BLOCKED"
    elif claim == "DONE" and not missing:
        status = "DONE"
    else:
        status = "INCOMPLETE"

    # report.md: the collector's framing, the member's response under its marked section
    header = ("Collected by Crown (`crown local collect`) at %s from the member's captured response.\n"
              "The member did not write this file. The member's raw response is preserved unedited as\n"
              "its own artifact at `%s` in this directory (sha256 %s) and is reproduced below,\n"
              "unchanged, under the marked heading. The collected manifest's values carry provenance\n"
              "grades; the collector's own checks are recorded in `collection-evidence.json`.\n\n"
              "## Member response (verbatim, collected)\n\n" % (now, src_ref, sha))
    with open(os.path.join(OUT, "report.md"), "wb") as f:
        f.write(header.encode("utf-8"))
        f.write(raw if raw.endswith(b"\n") else raw + b"\n")

    # deviations: the collector's self-identification first, then the evidence's own notes
    deviations = [
        "This manifest was generated by crown collection from the member's captured response; the member did not write it.",
        "The member's response is preserved unedited as its own artifact at %s (sha256 %s); report.md reproduces it under the marked section 'Member response (verbatim, collected)'." % (src_ref, sha),
    ]
    deviations += ["member-stated: %s" % d for d in member_dev]
    if src_kind == "session" and not deposit_meta:
        deviations.append("The in-session response was deposited without a source record (RUN/response.source.json); its runtime and session are recorded as unknown.")
    if files_stated is not None and sorted(files_stated) != sorted(tree_paths):
        deviations.append("The member stated files changed %s; the clone at collection holds %s. Both are recorded; neither was altered." % (files_stated, tree_paths))
    if tree_paths and files_stated is None:
        deviations.append("The clone holds working-tree path(s) %s the member's response does not account for; recorded as found, not attributed." % tree_paths)
    if status == "INCOMPLETE":
        deviations += ["Incomplete: %s." % m for m in missing]
        if not missing:
            deviations.append("Incomplete: the response could not support a complete record.")

    prov = {
        "status": "member-stated" if (claim and status == claim) else "crown-observed",
        "task": "crown-observed",
        "base": "crown-observed",
        "branch": "crown-observed",
        "commits": {"grade": "crown-verified", "check": "the clone's commits past the base, counted by the collector",
                    "ref": "collection-evidence.json#clone-state"},
        "artifacts": "crown-observed",
        "deviations": "crown-observed",
        "environment": env_grade,
    }
    man = {"status": status}
    if status == "BLOCKED":
        man["blocked_reason"] = reason
        prov["blocked_reason"] = "member-stated"
    man["task"] = TASK
    man["base"] = {"branch": BASE, "sha": BASE_SHA}
    man["branch"] = BASE
    man["commits"] = []
    if done is not None:
        man["done"] = done
    prov["done"] = done_grade
    man["gates"] = []
    prov["gates"] = "unknown"
    man["touched_paths"] = files_stated if files_stated is not None else tree_paths
    prov["touched_paths"] = ("member-stated" if files_stated is not None else
                             {"grade": "crown-verified", "check": "the clone's working-tree state at collection",
                              "ref": "collection-evidence.json#clone-state"})
    man["deviations"] = deviations
    if noticed is not None:
        man["noticed_not_acted_on"] = noticed
    prov["noticed_not_acted_on"] = "member-stated" if noticed is not None else "unknown"
    man["artifacts"] = [{"path": "report.md", "kind": "report"},
                        {"path": src_ref, "kind": "other"},
                        {"path": "collection-evidence.json", "kind": "other"}]
    if env:
        man["environment"] = env
    man["collection"] = {
        "collected_by": "crown local collect",
        "collected_at": now,
        "source": {"kind": src_kind, "ref": src_ref, "run": os.path.basename(RUN), "sha256": sha},
        "provenance": prov,
    }
    with open(mpath, "w") as f:
        json.dump(man, f, indent=2)
        f.write("\n")
    print("collected %s: status %s from the %s response (sha256 %s)" % (RUN, status, src_kind, sha[:12]))
    print("the record is collected, not gated: crown review check %s decides whether it passes" % OUT)
    if status == "INCOMPLETE":
        print("note: an INCOMPLETE record never passes review check; its deviations name what is missing")

if __name__ == "__main__":
    main()
