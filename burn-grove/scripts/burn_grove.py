#!/usr/bin/env python3
"""Safely close Herdr tabs and delete one issue-linked Grove workspace."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any, TextIO
from urllib.parse import urlparse


ISSUE_KEY_RE = re.compile(r"(?<![A-Z0-9])([A-Z][A-Z0-9]+-\d+)(?![A-Z0-9])", re.IGNORECASE)
Runner = Callable[[list[str]], subprocess.CompletedProcess[str]]


class BurnError(RuntimeError):
    """A failure that must stop destructive cleanup."""


def run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, text=True, capture_output=True, check=False)
    except OSError as exc:
        raise BurnError(f"could not run {command[0]}: {exc}") from exc


def parse_issue_key(issue_url: str, provider: str) -> str:
    if provider not in {"jira", "linear"}:
        raise BurnError(f"unsupported issue provider: {provider}")
    parsed = urlparse(issue_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise BurnError(f"--{provider}-url must be a full HTTP(S) issue URL")
    if provider == "linear":
        if parsed.netloc.lower() not in {"linear.app", "www.linear.app"}:
            raise BurnError("--linear-url must use the linear.app host")
        match = re.search(r"/issue/([A-Z][A-Z0-9]+-\d+)(?:/|$)", parsed.path, re.IGNORECASE)
    else:
        if parsed.netloc.lower() in {"linear.app", "www.linear.app"}:
            raise BurnError("use --linear-url for linear.app issue URLs")
        match = ISSUE_KEY_RE.search(parsed.path)
    if not match:
        raise BurnError(f"could not find an issue key in --{provider}-url")
    return match.group(1).upper()


def command_failure(command: list[str], proc: subprocess.CompletedProcess[str]) -> str:
    detail = proc.stderr.strip() or proc.stdout.strip() or f"exit code {proc.returncode}"
    return f"{' '.join(command)} failed: {detail}"


def load_json(command: list[str], runner: Runner) -> Any:
    proc = runner(command)
    if proc.returncode != 0:
        raise BurnError(command_failure(command, proc))
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise BurnError(f"{' '.join(command)} returned invalid JSON") from exc


def find_workspace(workspaces: Any, provider: str, issue_key: str) -> dict[str, Any]:
    if not isinstance(workspaces, list):
        raise BurnError("gw ws list --json returned an unexpected payload")
    matches = []
    for workspace in workspaces:
        if not isinstance(workspace, dict):
            continue
        source = workspace.get("source")
        if not isinstance(source, dict):
            continue
        source_provider = source.get("provider")
        source_ref = source.get("ref")
        if source_provider == provider and isinstance(source_ref, str) and source_ref.upper() == issue_key:
            matches.append(workspace)
    if not matches:
        raise BurnError(f"no Grove workspace has {provider} source.ref {issue_key}")
    if len(matches) != 1:
        raise BurnError(f"found {len(matches)} Grove workspaces with {provider} source.ref {issue_key}")
    return matches[0]


def absolute_path(value: Any, *, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise BurnError(f"{label} is missing")
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise BurnError(f"{label} must be absolute: {value}")
    resolved = path.resolve(strict=False)
    if resolved == Path(resolved.anchor):
        raise BurnError(f"{label} cannot be a filesystem root: {value}")
    return resolved


def is_path_within(value: Any, root: Path) -> bool:
    if not isinstance(value, str) or not value:
        return False
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        return False
    try:
        candidate.resolve(strict=False).relative_to(root.resolve(strict=False))
    except ValueError:
        return False
    return True


def validate_workspace(workspace: dict[str, Any]) -> tuple[str, Path, list[dict[str, Any]]]:
    name = workspace.get("name")
    if not isinstance(name, str) or not name:
        raise BurnError("matched Grove workspace has no name")
    root = absolute_path(workspace.get("path"), label="Grove workspace path")
    if not root.is_dir():
        raise BurnError(f"Grove workspace path is not a directory: {root}")
    repos = workspace.get("repos", [])
    if not isinstance(repos, list) or any(not isinstance(repo, dict) for repo in repos):
        raise BurnError("matched Grove workspace has invalid repository metadata")
    return name, root, repos


def result_items(payload: Any, key: str, command: list[str]) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        raise BurnError(f"{' '.join(command)} returned an unexpected payload")
    result = payload.get("result")
    items = result.get(key) if isinstance(result, dict) else None
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise BurnError(f"{' '.join(command)} returned an unexpected payload")
    return items


def inspect_herdr(runner: Runner) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    workspace_command = ["herdr", "workspace", "list"]
    herdr_payload = load_json(workspace_command, runner)
    herdr_workspaces = result_items(herdr_payload, "workspaces", workspace_command)
    tabs: list[dict[str, Any]] = []
    panes: list[dict[str, Any]] = []
    for herdr_workspace in herdr_workspaces:
        workspace_id = herdr_workspace.get("workspace_id")
        if not isinstance(workspace_id, str) or not workspace_id:
            raise BurnError("Herdr returned a workspace without a workspace_id")
        tab_command = ["herdr", "tab", "list", "--workspace", workspace_id]
        pane_command = ["herdr", "pane", "list", "--workspace", workspace_id]
        tabs.extend(result_items(load_json(tab_command, runner), "tabs", tab_command))
        panes.extend(result_items(load_json(pane_command, runner), "panes", pane_command))
    return tabs, panes


def find_associated_tabs(
    workspace_name: str,
    workspace_root: Path,
    tabs: Iterable[dict[str, Any]],
    panes: Iterable[dict[str, Any]],
) -> list[str]:
    associated_pane_tabs = {
        pane.get("tab_id")
        for pane in panes
        if isinstance(pane.get("tab_id"), str)
        and (
            is_path_within(pane.get("cwd"), workspace_root)
            or is_path_within(pane.get("foreground_cwd"), workspace_root)
        )
    }
    matches = []
    for tab in tabs:
        tab_id = tab.get("tab_id")
        if tab.get("label") == workspace_name and tab_id in associated_pane_tabs:
            matches.append(tab_id)
    return matches


def inspect_repositories(
    repos: Iterable[dict[str, Any]], workspace_root: Path, runner: Runner
) -> list[tuple[str, Path, list[str]]]:
    statuses = []
    for repo in repos:
        name = repo.get("repo_name")
        display_name = name if isinstance(name, str) and name else "<unnamed>"
        raw_path = repo.get("worktree_path")
        path = absolute_path(raw_path, label=f"worktree path for {display_name}")
        if not is_path_within(str(path), workspace_root):
            raise BurnError(f"worktree path escapes the Grove workspace: {path}")
        if not path.is_dir():
            raise BurnError(f"worktree path is not a directory: {path}")
        command = ["git", "-C", str(path), "status", "--porcelain=v1", "--untracked-files=all"]
        proc = runner(command)
        if proc.returncode != 0:
            raise BurnError(command_failure(command, proc))
        statuses.append((display_name, path, proc.stdout.splitlines()))
    return statuses


def print_plan(
    provider: str,
    issue_key: str,
    workspace_name: str,
    workspace_root: Path,
    tab_ids: list[str],
    statuses: list[tuple[str, Path, list[str]]],
    output: TextIO,
) -> None:
    print(f"Issue: {provider} {issue_key}", file=output)
    print(f"Grove workspace: {workspace_name}", file=output)
    print(f"Workspace path: {workspace_root}", file=output)
    print(f"Herdr tabs to close ({len(tab_ids)}): {', '.join(tab_ids)}", file=output)
    print("Repository status:", file=output)
    if not statuses:
        print("  (no repositories)", file=output)
    for name, path, lines in statuses:
        state = "DIRTY" if lines else "clean"
        print(f"  {name}: {state} ({path})", file=output)
        for line in lines:
            print(f"    {line}", file=output)


def cleanup(workspace_name: str, tab_ids: Iterable[str], runner: Runner) -> None:
    close_failures = []
    for tab_id in tab_ids:
        command = ["herdr", "tab", "close", tab_id]
        proc = runner(command)
        if proc.returncode != 0:
            close_failures.append(command_failure(command, proc))
    if close_failures:
        raise BurnError(
            "workspace was not deleted because Herdr tab closure failed: "
            + "; ".join(close_failures)
        )

    delete_command = ["gw", "delete", workspace_name, "--force"]
    proc = runner(delete_command)
    if proc.returncode != 0:
        raise BurnError(
            "all associated Herdr tabs were closed, but Grove workspace deletion failed: "
            + command_failure(delete_command, proc)
        )


def burn(
    issue_url: str,
    provider: str,
    *,
    runner: Runner = run_command,
    output: TextIO = sys.stdout,
) -> bool:
    issue_key = parse_issue_key(issue_url, provider)
    workspace = find_workspace(
        load_json(["gw", "ws", "list", "--json"], runner), provider, issue_key
    )
    workspace_name, workspace_root, repos = validate_workspace(workspace)
    tabs, panes = inspect_herdr(runner)
    tab_ids = find_associated_tabs(workspace_name, workspace_root, tabs, panes)
    if not tab_ids:
        raise BurnError("no associated Herdr tab matched both workspace name and path")
    statuses = inspect_repositories(repos, workspace_root, runner)
    print_plan(provider, issue_key, workspace_name, workspace_root, tab_ids, statuses, output)
    cleanup(workspace_name, tab_ids, runner)
    print(f"Deleted Grove workspace {workspace_name} after closing {len(tab_ids)} Herdr tab(s).", file=output)
    return True


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Close Herdr tabs and delete one Jira- or Linear-linked Grove workspace."
    )
    urls = parser.add_mutually_exclusive_group(required=True)
    urls.add_argument("--jira-url", help="Full HTTP(S) Jira issue URL")
    urls.add_argument("--linear-url", help="Full HTTP(S) Linear issue URL")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.linear_url:
            burn(args.linear_url, "linear")
        else:
            burn(args.jira_url, "jira")
    except BurnError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    os.environ.setdefault("GIT_TERMINAL_PROMPT", "0")
    raise SystemExit(main())
