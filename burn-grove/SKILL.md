---
name: burn-grove
description: Destroy the single Grove workspace linked to a Jira or Linear issue after exact metadata, path, tab, and repository checks. Use when the user invokes /burn-grove with a full issue URL or asks to remove, delete, or burn an issue-linked Grove workspace and its associated Herdr tabs.
---

# Burn Grove

Destroy a Jira- or Linear-linked Grove workspace only through the bundled safety-checked script.

## Workflow

1. Require exactly one full HTTP(S) Jira or `linear.app` issue URL. Reject a
   bare issue key.
2. From this skill directory, run the script in an interactive terminal:

   ```bash
   python3 scripts/burn_grove.py --jira-url "<full-jira-issue-url>"
   ```

   For Linear, use `--linear-url "<full-linear-issue-url>"`. Never pass both.

3. Let the script identify the workspace, inspect every repository, discover all
   associated Herdr tabs, and perform cleanup after its safety checks pass.
4. Never bypass the script with direct `herdr` or `gw` cleanup commands.
5. Report the script's result, including any partial cleanup if tabs closed but
   Grove deletion failed.

## Safety guarantees

- Match exactly one workspace using only the URL-derived provider (`jira` or
  `linear`) and issue key in `source.ref`; never fall back to a workspace name
  or slug.
- Match a Herdr tab only when its label exactly equals the Grove workspace name
  and one of its panes is rooted inside the Grove workspace path.
- Refuse deletion when the workspace match is missing or ambiguous, no
  associated Herdr tab exists, a repository cannot be inspected, or a path
  escapes the workspace.
- Display clean, dirty, and untracked repository state before cleanup.
- Close all associated tabs before invoking `gw delete <workspace> --force`.
  Abort Grove deletion if any tab fails to close.

## Requirements

Require Python 3, Git, Grove's `gw` CLI, a running Herdr session, and permission
to access their local state.

## Script

Use `scripts/burn_grove.py`. Run it with `--help` to inspect its interface.
