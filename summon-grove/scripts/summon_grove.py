#!/usr/bin/env python3
"""Create or reuse a Grove workspace for an issue URL and focus it in Herdr."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ISSUE_KEY_RE = re.compile(r"\b([A-Z][A-Z0-9]+-\d+)\b", re.IGNORECASE)
MAX_WORKSPACE_LEN = 32


@dataclass
class Result:
    provider: str
    issue_key: str
    title: str
    workspace: str
    branch: str
    path: str
    workspace_action: str
    tab_action: str
    warnings: list[str]


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True, check=check)


def require_command(name: str) -> None:
    if shutil.which(name) is None:
        raise SystemExit(f"error: required command not found on PATH: {name}")


def parse_issue_key(issue_url: str, provider: str) -> str:
    if provider not in {"jira", "linear"}:
        raise SystemExit(f"error: unsupported issue provider: {provider}")
    parsed = urlparse(issue_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SystemExit(f"error: --{provider}-url must be a full http(s) issue URL")
    if provider == "linear":
        if parsed.netloc.lower() not in {"linear.app", "www.linear.app"}:
            raise SystemExit("error: --linear-url must use the linear.app host")
        match = re.search(r"/issue/([A-Z][A-Z0-9]+-\d+)(?:/|$)", parsed.path, re.IGNORECASE)
    else:
        if parsed.netloc.lower() in {"linear.app", "www.linear.app"}:
            raise SystemExit("error: use --linear-url for linear.app issue URLs")
        match = ISSUE_KEY_RE.search(parsed.path)
    if not match:
        raise SystemExit(f"error: could not find an issue key in --{provider}-url")
    return match.group(1).upper()


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return slug


def derive_workspace_name(issue_key: str, title: str) -> str:
    key_slug = issue_key.lower()
    title_slug = slugify(title)
    if not title_slug:
        return key_slug
    prefix = f"{key_slug}-"
    available = MAX_WORKSPACE_LEN - len(prefix)
    words = title_slug.split("-")
    trimmed_words: list[str] = []
    length = 0
    for word in words:
        next_length = length + len(word) + (1 if trimmed_words else 0)
        if next_length > available:
            break
        trimmed_words.append(word)
        length = next_length
    trimmed_title = "-".join(trimmed_words)
    if not trimmed_title and available > 0:
        trimmed_title = title_slug[:available].rstrip("-")
    return f"{prefix}{trimmed_title}" if trimmed_title else key_slug


def source_title(issue_key: str, title: str) -> str:
    if issue_key.lower() in title.lower():
        return title
    return f"{issue_key}: {title}"


def fetch_jira_title_with_acli(issue_key: str, warnings: list[str]) -> str:
    if shutil.which("acli") is None:
        warnings.append("acli not found; using Jira key as title fallback")
        return issue_key
    try:
        proc = run(
            ["acli", "jira", "workitem", "view", issue_key, "--fields", "summary", "--json"],
            check=True,
        )
        payload = json.loads(proc.stdout)
        summary = payload.get("fields", {}).get("summary")
        if isinstance(summary, str) and summary.strip():
            return summary.strip()
        warnings.append("acli returned no Jira summary; using Jira key as title fallback")
    except (subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        warnings.append(f"could not fetch Jira summary with acli: {exc}")
    return issue_key


def issue_source(args: argparse.Namespace) -> tuple[str, str]:
    if args.linear_url:
        return "linear", args.linear_url
    return "jira", args.jira_url


def json_from(cmd: list[str]) -> dict[str, Any] | None:
    proc = run(cmd, check=False)
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


def workspace_path(workspace: str) -> str | None:
    payload = json_from(["gw", "ws", "show", workspace, "--json"])
    if not payload:
        return None
    path = payload.get("path")
    if isinstance(path, str) and path:
        return str(Path(path).expanduser())
    return None


def create_workspace(
    *,
    workspace: str,
    branch: str,
    preset: str,
    provider: str,
    issue_url: str,
    issue_key: str,
    title: str,
) -> str:
    cmd = [
        "gw",
        "create",
        workspace,
        "--preset",
        preset,
        "--branch",
        branch,
        "--source-provider",
        provider,
        "--source-url",
        issue_url,
        "--source-ref",
        issue_key,
        "--source-title",
        title,
    ]
    proc = run(cmd, check=False)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        sys.stderr.write(proc.stdout)
        raise SystemExit(proc.returncode)
    path = workspace_path(workspace)
    if not path:
        raise SystemExit("error: workspace was created but path could not be read from gw")
    return path


def find_herdr_tab(label: str) -> str | None:
    payload = json_from(["herdr", "tab", "list"])
    tabs = ((payload or {}).get("result") or {}).get("tabs") or []
    for tab in tabs:
        if tab.get("label") == label and isinstance(tab.get("tab_id"), str):
            return tab["tab_id"]
    return None


def focus_or_create_tab(label: str, cwd: str, warnings: list[str]) -> str:
    tab_id = find_herdr_tab(label)
    if tab_id:
        proc = run(["herdr", "tab", "focus", tab_id], check=False)
        if proc.returncode == 0:
            return "reused"
        warnings.append(f"could not focus existing Herdr tab {tab_id}: {proc.stderr.strip()}")

    proc = run(["herdr", "tab", "create", "--cwd", cwd, "--label", label, "--focus"], check=False)
    if proc.returncode != 0:
        warnings.append(
            "could not create Herdr tab; start Herdr and rerun: "
            + (proc.stderr.strip() or proc.stdout.strip())
        )
        return "failed"
    return "created"


def summon(args: argparse.Namespace) -> Result:
    warnings: list[str] = []
    require_command("gw")
    require_command("herdr")

    provider, issue_url = issue_source(args)
    issue_key = parse_issue_key(issue_url, provider)
    if args.title:
        title = args.title.strip()
    elif provider == "jira":
        title = fetch_jira_title_with_acli(issue_key, warnings)
    else:
        warnings.append("Linear title not supplied; using issue key as title fallback")
        title = issue_key
    source = source_title(issue_key, title)
    workspace = derive_workspace_name(issue_key, title)
    branch = workspace

    if args.dry_run:
        return Result(provider, issue_key, source, workspace, branch, "", "dry-run", "dry-run", warnings)

    path = workspace_path(workspace)
    if path:
        workspace_action = "reused"
    else:
        path = create_workspace(
            workspace=workspace,
            branch=branch,
            preset=args.preset,
            provider=provider,
            issue_url=issue_url,
            issue_key=issue_key,
            title=source,
        )
        workspace_action = "created"

    tab_action = focus_or_create_tab(workspace, path, warnings)
    return Result(
        provider,
        issue_key,
        source,
        workspace,
        branch,
        path,
        workspace_action,
        tab_action,
        warnings,
    )


def print_result(result: Result, *, as_json: bool) -> None:
    payload = {
        "provider": result.provider,
        "issue_key": result.issue_key,
        "title": result.title,
        "workspace": result.workspace,
        "branch": result.branch,
        "path": result.path,
        "workspace_action": result.workspace_action,
        "tab_action": result.tab_action,
        "warnings": result.warnings,
    }
    if result.provider == "jira":
        payload["jira_key"] = result.issue_key
    if as_json:
        print(json.dumps(payload, indent=2))
        return

    print(f"workspace: {result.workspace} ({result.workspace_action})")
    print(f"branch: {result.branch}")
    if result.path:
        print(f"path: {result.path}")
    print(f"herdr tab: {result.tab_action}")
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create or reuse a Grove workspace from a Jira or Linear URL and focus it in Herdr.",
    )
    urls = parser.add_mutually_exclusive_group(required=True)
    urls.add_argument("--jira-url", help="Full Jira issue URL")
    urls.add_argument("--linear-url", help="Full Linear issue URL")
    parser.add_argument("--preset", required=True, help="Grove preset name")
    parser.add_argument("--title", default="", help="Issue title/summary")
    parser.add_argument("--dry-run", action="store_true", help="Derive names without creating anything")
    parser.add_argument("--json", action="store_true", help="Print structured JSON output")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    result = summon(args)
    print_result(result, as_json=args.json)
    return 0


if __name__ == "__main__":
    os.environ.setdefault("GIT_TERMINAL_PROMPT", "0")
    raise SystemExit(main())
