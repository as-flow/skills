# Multi-agent workflows with Grove and Herdr

This guide describes a solo-operator workflow for managing multi-repo coding
work with Grove workspaces and a single global Herdr session.

## Mental model

- **Grove** creates one task workspace containing Git worktrees from the repos
  in a preset. Each workspace gets one shared branch name.
- **Herdr** keeps all terminal work visible in one persistent terminal
  multiplexer. Use one Herdr tab per Grove workspace.
- **Agents** are started manually inside Herdr panes. The setup command only
  creates the workspace and opens the right tab.

## Prerequisites

Install the tools:

```bash
brew install nicksenap/grove/grove
curl -fsSL https://herdr.dev/install.sh | sh
```

Install the Herdr agent skill so agents running inside Herdr panes can
coordinate through Herdr:

```bash
npx skills add ogulcancelik/herdr --skill herdr -g
```

Install this workflow skill:

```bash
npx skills add as-flow/skills --skill summon-grove -g
```

Initialize Grove with the directories that contain your source repositories:

```bash
gw init ~/path/to/repos
gw explore
```

Add shell integration so `gw go` changes the current directory:

```bash
eval "$(gw shell-init)"
```

Create Grove presets for common repo groups:

```bash
gw preset add backend -r api,worker,auth
gw preset add frontend -r web,design-system
gw preset list
```

Start Herdr once and keep using the default global session:

```bash
herdr
```

## Start a task

Invoke the skill with a Jira URL and a Grove preset:

```text
/summon-grove https://your-domain.atlassian.net/browse/ENG-123 backend
```

The skill will:

1. Read the Jira issue key from the URL.
2. Fetch the issue title through the agent's Jira tools when available, or let
   the bundled script fall back to `acli`.
3. Derive a workspace and branch name like
   `eng-123-short-ticket-title`.
4. Reuse an existing Grove workspace with that name, or create one with:

   ```bash
   gw create eng-123-short-ticket-title \
     --preset backend \
     --branch eng-123-short-ticket-title \
     --source-provider jira \
     --source-url https://your-domain.atlassian.net/browse/ENG-123 \
     --source-ref ENG-123 \
     --source-title "ENG-123: Short ticket title"
   ```

5. Reuse or create a Herdr tab labeled with the workspace name and rooted at
   the Grove workspace path.

The command is intentionally non-destructive. It never deletes or replaces a
workspace.

## Work in Herdr

Use the Herdr tab as the task's control surface:

```bash
gw status
gw sync
gw run
```

Create panes manually for the repos or subtasks that need agents. Start agents
inside the appropriate repo directories. Because the agents run inside Herdr,
the Herdr agent skill can let them inspect panes, wait on other agents, split
panes, and coordinate without leaving the terminal workspace.

Recommended pane pattern:

- One shell at the Grove workspace root for `gw status`, `gw sync`, and final
  checks.
- One pane per active repo or subtask.
- Extra panes only when they serve a specific purpose, such as tests, logs, or
  review.

Avoid starting an agent for every repo in a preset by default. Presets define
the possible work area, not the number of agents required.

## During the task

Useful Grove commands:

```bash
gw status
gw sync
gw add-repo <workspace> -r <repo>
gw remove-repo <workspace> -r <repo>
gw run
```

Useful Herdr commands:

```bash
herdr tab list
herdr pane list
herdr agent list
```

Detach from Herdr without stopping work:

```text
ctrl+b q
```

Reattach later:

```bash
herdr
```

## Finish a task

Before cleanup:

1. Check each changed repo.
2. Run repo-specific validators.
3. Commit and open PRs as appropriate for each repo.
4. Confirm there is no uncommitted work:

   ```bash
   gw status <workspace>
   ```

When the task is truly done, delete the Grove workspace explicitly:

```bash
gw delete <workspace>
```

Do not wire cleanup into `/summon-grove`. Starting work and deleting work are
separate operations on purpose.

## Safety rules

- Use a Jira URL, not a bare issue key.
- Keep presets small enough to match a real task slice.
- Reuse existing workspaces instead of replacing them.
- Do not force-delete workspaces with unreviewed changes.
- Start agents only for active repos or subtasks.
- Keep secrets out of Grove hooks, skill files, and workspace names.

## Troubleshooting

- **Preset not found**: run `gw preset list`, then rerun with an existing preset.
- **Jira title missing**: authenticate the agent's Jira integration or `acli`.
- **Herdr tab not created**: start Herdr once with `herdr`, then rerun the
  summon command.
- **Wrong directory**: run `gw go <workspace>` from any shell to jump back to
  the Grove workspace.
- **Need more repos**: use `gw add-repo <workspace> -r <repo>` instead of
  creating a second workspace for the same task.
