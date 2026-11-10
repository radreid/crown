---
name: crown-instances
description: The workers a project dispatches to. Local members - add, refresh, list (STALE, DRIFT), profiles and tiers, and `crown agent for ROLE [--profile P]` to pick member, model and effort. Cloud instances (cloud agents) - register, list, inspect, budget, refresh-prompt, normalize, remove. Load it to manage members, models, effort, dispatch or cloud instances.
argument-hint: agent add|list|models|refresh|for ... | instances init|list|show|remove ...
---

# /crown-instances

The registry (`~/.crown/config/instances.json`) and the
session tracker (`~/.crown/state/sessions.json`) are per user and never in a repository. Plans, tokens and `--approved`:
`crown help approvals`.

## Models and members (local)

There are two base members, one per guard class (`crown help guard`): `worker` (roles build, write and test; write class)
and `reviewer` (review; read-only). Everything else is a profile, resolved at dispatch: a base, a tier (fast, balanced, deep,
frontier; the project's `models.provider` maps tiers to models; there is no default provider), an
effort and a purpose. Shipped profiles: `build`, `write`, `test` (worker); `review`, `auditor`, `advisor` (reviewer);
`researcher`, `lead`. A project adds or overrides `profiles.<name>`.

- `crown agent models [--project P] [--json]`: the bases, profiles and members of one project (exit 2 with none in effect). `crown agent list` shows every project's members.
- `crown agent add NAME --roles LIST --project P` (`--project` is required; `worker` and `reviewer` default to their base's
  roles): one neutral definition is rendered by the project's local runtime (`models.provider.local`), model and effort mapped
  through its catalog. The render is kept in `~/.crown/config/agents/P/`, outside every repository, and written to the
  project's member render (`~/.crown/state/render/P/RUNTIME.agents`, linked into a work tree by
  `crown project link P --resource agents`) or to the checkout's own agents directory, hidden from git. A project with no local
  runtime or agent files is refused (exit 2).
- `agent list` and `agent models` flag a member `MISSING` (the file is gone: a cleaned checkout, a fresh clone), `STALE` (the
  copy in config is gone, or the definition, catalog, renderer or an extension changed since) or `DRIFT` (edited by hand), each
  with its fix: `crown agent refresh NAME --project P` writes copy and file again, keeping name, roles and model; a `DRIFT`
  file is replaced, so look at the edit first.
- **Dispatch**: `crown agent for ROLE [--profile NAME] [--project P]` prints one line, `MEMBER MODEL EFFORT PROFILE` (MODEL is
  the alias, `-` when none). Spawn it as `crown provider notes spawn` says. A profile whose base does not fit the role is
  refused. Per-task diff checks: `--profile auditor` on review (fast, low effort). Search is not a role:
  `crown provider notes exploration`. Your own session model is set in the runtime (`crown provider notes session-model`); the
  `lead` profile has no base, is never dispatched, and its tier is the recommendation. Frontier is opt-in: `--profile researcher`
  only when the owner or you name it for the task.
- `crown instances init --location local --agent FILE [--name N] [--model M] [--effort E]` records a local agent file's path, sha256, model and effort.
- With the runtime's `dispatch.mode` `command` there is no member file: `crown local run RUN` runs the CLI with the member's
  prompt composed in (`/crown-task`).

## Cloud instances

Cloud verbs need `--asked "<the user's request that names the cloud instance>"`; changes to existing resources also need
`--approved` after you have shown the printed PLAN.

| Verb | Command | Notes |
|---|---|---|
| init (existing) | `crown instances init --location cloud --deployment ID [--name N] [--budget CENTS] [--model M] [--effort E] [--no-session] --asked "..." [--approved "..."]` | Records the deployment and its agent, starts a standby session and tracks it. A differing `--model` or `--effort` prints a PLAN; with `--approved` the agent gets a new version and the deployment is re-pointed. |
| init (new) | `crown instances init --location cloud --provision --name N [--model M] [--effort E] [--budget CENTS] [--apt "pkg ..."] [--networking unrestricted\|limited] --asked "..." [--approved "..."]` | Plan without `--approved`; with it, creates the resources via `/crown-provision`, seeds both memory stores, registers and starts a session. |
| list | `crown instances list [--reconcile]` | Instances (`prompt STALE` when the prompt changed since it was pushed) and active sessions; `--reconcile` flags live sessions missing from the tracker (ORPHAN, never touched). |
| show | `crown instances show NAME [--reconcile]` | The record plus staleness: prompt hash, agent newer than pinned, changed agent file, archived or paused deployment; NAMING lines. |
| budget | `crown instances budget NAME CENTS --asked "..." [--session SID]` | The deployment's spend ceiling, inherited by new sessions; `--session` also changes a running session that has a budget. |
| refresh-prompt | `crown instances refresh-prompt NAME [--if-stale] --asked "..." [--plan TOKEN --approved "..."]` | Rebuilds the cloud agent's prompt from the current contract, preamble and role addendum, prints a plan token; applying creates a new agent version and re-points the deployment. Run it when the contract changes. |
| normalize | `crown instances normalize NAME --asked "..." [--approved "..."]` | Renames the agent, environment, deployment and stores to the `<project>-...` names; plan first. |
| remove | `crown instances remove NAME` | Registry entry only; refuses with open sessions. |

Instance names are `<project>-<role>` with a role from the fixed list (`build`, `review`, `write`, `test`, `lead`), for example
`myproject-build`, or a base: `<project>-worker` (class write) or `<project>-reviewer` (read-only; first accept the missing cloud
read-only barrier with `crown provider accept NAME --surface cloud --no-barrier`). An existing deployment needs a conforming `--name`.
