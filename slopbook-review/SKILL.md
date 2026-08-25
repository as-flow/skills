---
name: slopbook-review
description: Review a PR with both /review-slop and /code-review, using the matching /to-slopbook summary spec as the spec source.
---

# Slopbook Review

Use this skill when the user invokes:

```text
/slopbook-review <PR URL|number|branch> [slopbook-spec-path]
```

The command runs two independent review subagents:

1. `/review-slop` on the PR.
2. `/code-review` on the PR against `main`, using the Slopbook summary spec
   created by `/to-slopbook`.

## Workflow

1. Require a PR argument. If it is missing, ask the user for the PR URL, number,
   or branch.
2. Locate the Slopbook spec:
   - If a second argument is present, treat it as the spec path and verify it
     exists.
   - Otherwise, derive the same PR slug as `/to-slopbook`: for a PR URL, use
     `host-owner-repo-pr-number`; for a PR number in a GitHub repo, use
     `owner-repo-pr-number`; for a branch-only argument, use the branch name.
     Lowercase it, replace non-alphanumeric runs with `-`, and trim leading or
     trailing `-`.
   - Resolve the OS temp directory, look under `<temp>/slopbook/`, and select
     the newest `latest-<pr-slug>.md` or `slopbook-<pr-slug>-*.md` file
     matching the PR.
   - If no matching spec is found, ask the user to run
     `/to-slopbook <PR>` or provide a spec path.
3. Resolve the PR metadata with `gh pr view <PR> --json url,title,headRefName,
   headRepositoryOwner,headRepository,headRefOid,baseRefName,baseRepository,
   baseRefOid`. Do not run `gh pr checkout`, `git checkout`, `git switch`, or
   any command that changes the local branch.
4. Confirm the target branch is `main`. If the PR targets a different branch,
   stop and tell the user `/slopbook-review` is defined to review PRs against
   `main`.
5. Collect the diff only through the GitHub CLI:
   - Use `gh pr diff <PR> --patch` for the full patch.
   - Use `gh pr diff <PR> --name-only` for the file list.
   - Use `gh pr view <PR>` for title, body, linked issues, and metadata.
   Do not rely on local `git diff`, local branch state, or branch checkouts.
6. Confirm the PR diff is non-empty before launching subagents.
7. Run the two subagents in parallel. Keep their contexts isolated.

## Subagent prompts

### Slop subagent

Ask the subagent to invoke `/review-slop` for the PR argument. Include:

- PR argument
- repository path
- PR branch if known
- PR metadata from `gh pr view`
- diff commands: `gh pr diff <PR> --patch` and
  `gh pr diff <PR> --name-only`
- instruction to read the actual PR diff, PR body, linked issues, and nearby
  code as required by `/review-slop`
- instruction not to check out, switch, fetch into, or otherwise mutate local
  branches
- instruction to return the `/review-slop` output format verbatim

### Code-review subagent

Ask the subagent to invoke `/code-review` for the PR diff against `main`, but
to supply the PR diff from `gh pr diff` rather than a local checkout.
Include:

- fixed point: `main`
- PR argument and branch
- repository path
- Slopbook spec path
- PR metadata from `gh pr view`
- diff commands: `gh pr diff <PR> --patch` and
  `gh pr diff <PR> --name-only`
- instruction that the Slopbook spec is the spec source for the Spec axis
- instruction not to use local `git diff`, `gh pr checkout`, `git checkout`,
  `git switch`, or any branch-changing command
- instruction to return the `/code-review` output format with `## Standards`
  and `## Spec` sections

## Aggregation format

Use this structure exactly:

```md
# Slopbook Review: <PR title or identifier>

## Inputs

- PR: <URL or identifier>
- Repository: <owner/repo or local path>
- Fixed point: <main or origin/main>
- Slopbook spec: <absolute path>

## /review-slop

<Slop subagent output>

## /code-review

<Code-review subagent output>

## Cross-review synthesis

- <Only high-confidence overlaps, contradictions, or blockers that emerge from
  comparing the two reviews. Write "None noted." if there are none.>

## Next actions

- <Concrete follow-up actions, ordered by severity. Write "None required." if
  both reviews found no actionable issues.>
```

## Constraints

- Do not merge the two review axes into a single reranked list. Preserve each
  skill's native output.
- Do not invent a spec. If the Slopbook spec is missing, stop and ask for it.
- Do not check out, switch, fetch into, or otherwise mutate local branches.
  Review only from `gh pr view` and `gh pr diff` output.
- Do not run the two reviews inline unless subagents are unavailable.
