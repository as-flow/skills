---
name: summon-grove
description: Create or reuse a Grove multi-repo workspace from a Jira or Linear issue URL and Grove preset, then open or focus a matching Herdr tab. Use when the user invokes /summon-grove or asks to summon a Grove workspace for an issue.
license: MIT
---

# Summon Grove

Use this skill when the user invokes:

```text
/summon-grove <jira-or-linear-url> <grove-preset>
```

The command creates or reuses a Grove workspace for the issue, then opens
or focuses a Herdr tab rooted at that workspace. It must not launch coding
agents, delete workspaces, replace worktrees, or force cleanup.

## Workflow

1. Parse exactly two arguments:
   - Issue URL: a full Jira or `linear.app` issue URL, not a bare issue key.
   - `grove-preset`: an existing Grove preset name.
2. Identify the provider and extract the issue key from the URL.
3. Fetch the issue title with the provider's native MCP tool:
   - For Jira, use the agent's Jira tools; if unavailable, omit the title and
     let the script try `acli jira workitem view`.
   - For Linear, use Linear's exact issue lookup with the extracted key. If it
     is unavailable, omit the title and let the script use the key.
4. From this skill directory, run:

   ```bash
   python3 scripts/summon_grove.py --jira-url "<jira-url>" --preset "<grove-preset>" --title "<issue title>"
   ```

   For Linear, use `--linear-url "<linear-url>"` instead of `--jira-url`.
   Exactly one URL flag is required. If you could not fetch a title, omit
   `--title`.
5. Report the workspace name, workspace path, and whether the workspace/tab was
   created or reused.

## Guarantees

- Workspace and branch names include the issue key and title slug, for example
  `we-17267-map-llm-gateway-traffic-to-frozen-v1`.
- Workspace and branch names are capped at 32 characters and truncate the title
  slug at word boundaries.
- Existing Grove workspaces are reused, never deleted or replaced.
- Existing Herdr tabs with the same label are focused, not duplicated.
- The script records exact provider metadata in Grove using
  `--source-provider jira|linear`, `--source-url`, `--source-ref`, and
  `--source-title`.

## Available script

- `scripts/summon_grove.py` creates/reuses the Grove workspace and Herdr tab.
  Run `python3 scripts/summon_grove.py --help` for the exact interface.

## Reference guide

- Read `references/user-guide.md` when the user asks how the Grove + Herdr
  workflow should be used end-to-end.

## Troubleshooting

- If `gw` is missing, install Grove first.
- If `herdr tab create` fails, start Herdr in a terminal and rerun the command.
- If title lookup fails, authenticate the matching Jira or Linear MCP. Jira can
  also fall back to `acli`.
- If the preset is missing, list presets with `gw preset list`.
