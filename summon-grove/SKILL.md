---
name: summon-grove
description: Create or reuse a Grove multi-repo workspace from a Jira URL and Grove preset, then open or focus a matching Herdr tab. Use when the user invokes /summon-grove or asks to summon a Grove workspace for a Jira ticket.
license: MIT
compatibility: Requires git, Python 3, Grove gw, Herdr, and Jira access through the agent's Jira tools or acli.
---

# Summon Grove

Use this skill when the user invokes:

```text
/summon-grove <jira-url> <grove-preset>
```

The command creates or reuses a Grove workspace for the Jira issue, then opens
or focuses a Herdr tab rooted at that workspace. It must not launch coding
agents, delete workspaces, replace worktrees, or force cleanup.

## Workflow

1. Parse exactly two arguments:
   - `jira-url`: a full Jira issue URL, not a bare ticket key.
   - `grove-preset`: an existing Grove preset name.
2. Extract the Jira key from the URL.
3. Fetch the Jira issue summary:
   - Prefer the agent's native Jira/MCP tools when available.
   - If native tools are unavailable, omit the title and let the script try
     `acli jira workitem view`.
4. From this skill directory, run:

   ```bash
   python3 scripts/summon_grove.py --jira-url "<jira-url>" --preset "<grove-preset>" --title "<jira summary>"
   ```

   If you could not fetch a title, omit `--title`.
5. Report the workspace name, workspace path, and whether the workspace/tab was
   created or reused.

## Guarantees

- Workspace and branch names include the Jira key and title slug, for example
  `we-17267-map-llm-gateway-traffic-to-frozen-v1`.
- Workspace and branch names are capped at 32 characters and truncate the title
  slug at word boundaries.
- Existing Grove workspaces are reused, never deleted or replaced.
- Existing Herdr tabs with the same label are focused, not duplicated.
- The script records Jira metadata in Grove with `--source-provider jira`,
  `--source-url`, `--source-ref`, and `--source-title`.

## Available script

- `scripts/summon_grove.py` creates/reuses the Grove workspace and Herdr tab.
  Run `python3 scripts/summon_grove.py --help` for the exact interface.

## Reference guide

- Read `references/user-guide.md` when the user asks how the Grove + Herdr
  workflow should be used end-to-end.

## Troubleshooting

- If `gw` is missing, install Grove first.
- If `herdr tab create` fails, start Herdr in a terminal and rerun the command.
- If Jira title lookup fails, authenticate the agent's Jira tools or `acli`.
- If the preset is missing, list presets with `gw preset list`.
