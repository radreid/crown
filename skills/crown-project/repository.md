Load when you link a work tree to the project's skills, agents and memory, or start a project from a repository.

# Link a work tree, start from a repository

**Link a work tree.** Run `crown project link NAME [--resource skills,agents,memory]` inside a
checkout or worktree (with no `--resource`, every one the runtime links and that exists). It
prints one plan and token for all of them (`crown help approvals`); applied, the project's skills, member files
and memory (the runtime's memory directory becomes a link into
`~/.crown/memory/projects/NAME`) load from `~/.crown` there, each placed the way the runtime
says: a directory link, one link per entry, or a copy. A real directory in the way moves to
`NAME.crown-backup`, never deleted; `crown project unlink NAME` undoes it. A worktree has its own
links, and nothing records which worktrees exist: run it in each.

**Start from a repository** instead of an answers file: `crown project new NAME` creates a new one on the
methodology's branches, `crown project attach [DIR]` reads an existing one (it shows the answers and the gaps and changes nothing in
the repository), and `crown project adopt NAME` then creates the missing long-lived branches and methodology files on a branch to
review. See `crown help project`.
