#!/usr/bin/env python3
"""Where crown keeps its per-user data: the one place the Python scripts ask. lib/lib.sh does the same for the shell
scripts (DA_CONF, DA_STATE); keep the two in step.

  configuration   CROWN_CONF, else <root>/config      (instances, projects, packs, credentials)
  state           CROWN_STATE, else <root>/state      (sessions, audit.log, runs, backups)
  root            CROWN_HOME, else <tool root>/.crown in a dev run (below), else ~/.crown

CROWN_CONF and CROWN_STATE win (tests use them); CROWN_HOME replaces the root. XDG_CONFIG_HOME and XDG_STATE_HOME are
not used for crown's own data (the ant CLI keeps its login under the former).

Installed and dev runs: `install.sh --user` records the tool root it installed in <live config>/install.json. A checkout
whose real path differs from that record, run without CROWN_HOME, CROWN_CONF or CROWN_STATE, is a dev run: it keeps its
data in <tool root>/.crown (git-ignored), so a branch checkout never touches live data. With no record, or the same
tool root, the run is the installed one and uses ~/.crown. The "live" locations (live_root, live_conf) are the ones an
installed run uses; the record is read from there.
Importing this module never creates anything. In a dev run banner() is the line the dispatcher's preamble (lib/help.py
preamble) prints to stderr before every command except help, version, __complete, __guard and the run-event hooks."""
import json, os


def tool_root():
    return os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


def explicit():
    """True when the person named a location, so there is no default to choose between."""
    return any(os.environ.get(k) for k in ("CROWN_CONF", "CROWN_STATE", "CROWN_HOME"))


def live_root():
    return os.environ.get("CROWN_HOME") or os.path.join(os.path.expanduser("~"), ".crown")


def live_conf():
    return os.environ.get("CROWN_CONF") or os.path.join(live_root(), "config")


def installed_tool_root():
    """The tool root install.sh recorded, or None (no record, or one that cannot be read)."""
    try:
        with open(os.path.join(live_conf(), "install.json")) as f:
            t = json.load(f).get("tool_root")
    except (OSError, ValueError, AttributeError):
        return None
    return os.path.realpath(t) if isinstance(t, str) and t else None


def dev_run():
    if explicit():
        return False
    rec = installed_tool_root()
    return rec is not None and rec != tool_root()


def root():
    if os.environ.get("CROWN_HOME"):
        return os.environ["CROWN_HOME"]
    return os.path.join(tool_root(), ".crown") if dev_run() else live_root()


def conf():
    return os.environ.get("CROWN_CONF") or os.path.join(root(), "config")


def state():
    return os.environ.get("CROWN_STATE") or os.path.join(root(), "state")


def banner():
    if not dev_run():
        return ""
    return "dev run from %s; data in %s (CROWN_HOME=~/.crown uses live data)" % (tool_root(), os.path.join(tool_root(), ".crown"))
