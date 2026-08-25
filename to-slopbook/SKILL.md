---
name: to-slopbook
description: Create a temporary Slopbook summary spec for a PR from the PR metadata and the user's surrounding context.
---

# To Slopbook

Use this skill when the user invokes:

```text
/to-slopbook <PR URL|number|branch>
```

The command creates a summary spec for review. It must save the document under
the operating system temporary directory, not the current workspace.

## Workflow

1. Require one PR argument. If it is missing, ask the user for the PR URL,
   number, or branch.
2. Identify the PR and collect lightweight metadata:
   - PR URL or identifier
   - repository, source branch, target branch
   - title, author, status, labels, and PR body when available
   - linked issues, docs, ADRs, and referenced commits when available
3. Ask the user for a single freeform context dump covering:
   - product intent and user problem
   - why the PR exists now
   - design constraints and discarded alternatives
   - ADRs, decisions, conclusions, and tradeoffs
   - rollout, migration, observability, and testing expectations
   - open questions, risks, non-goals, and reviewer focus areas
4. If the user provides only partial context, synthesize from what is available.
   Ask follow-up questions only when an answer is required to avoid a misleading
   spec.
5. Resolve the temp directory with the OS temp location. On macOS and Linux,
   prefer `${TMPDIR:-/tmp}`; otherwise use Python's
   `tempfile.gettempdir()`. Create a `slopbook` directory inside it.
6. Derive a deterministic PR slug:
   - For a PR URL, use `host-owner-repo-pr-number`.
   - For a PR number in a GitHub repo, use `owner-repo-pr-number`.
   - For a branch-only argument, use the branch name.
   - Lowercase it, replace non-alphanumeric runs with `-`, and trim leading or
     trailing `-`.
7. Save a Markdown file named:

   ```text
   slopbook-<pr-slug>-<YYYYMMDD-HHMMSS>.md
   ```

   Also update a latest pointer file for the same PR slug:

   ```text
   latest-<pr-slug>.md
   ```

8. Report both paths and tell the user to pass the latest path explicitly if
   `/slopbook-review` cannot auto-discover it.

## Summary spec template

Use this structure exactly:

```md
# Slopbook Summary Spec: <PR title or identifier>

## Metadata

- PR: <URL or identifier>
- Repository: <owner/repo or local path>
- Source branch: <branch>
- Target branch: <branch>
- Created from: /to-slopbook
- Created at: <ISO timestamp>

## Executive Summary

<Short synthesis of the change and why it matters.>

## Problem / Intent

<The problem, user impact, and intended outcome.>

## PR Scope and Approach

<What the PR changes and the implementation approach at a high level.>

## Context Provided by User

<Condensed context dump, preserving important nuance.>

## ADRs / Decisions

- <Decision>: <rationale, tradeoff, and consequence>

## Conclusions

- <Conclusion and why it is considered settled>

## Open Questions

- <Question, owner if known, and why it matters>

## Risks / Reviewer Focus Areas

- <Risk or area reviewers should inspect>

## Testing / Validation Expectations

- <Expected test, validation, rollout, or observability proof>

## Non-goals / Out of Scope

- <Explicitly excluded work>

## References

- <PR, issue, doc, ADR, commit, file path, or discussion link>
```

## Constraints

- Redact secrets, tokens, credentials, private keys, and sensitive personal data.
- Do not paste large diffs or duplicate long external artifacts. Reference them
  by path or URL.
- Preserve uncertainty. Put unresolved or contested points in `Open Questions`;
  do not turn them into decisions.
- Keep the spec useful for `/slopbook-review`: reviewers should be able to judge
  whether the PR matches the stated intent without reading the original
  conversation.
