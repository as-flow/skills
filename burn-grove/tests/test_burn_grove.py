from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "burn_grove.py"
SPEC = importlib.util.spec_from_file_location("burn_grove", SCRIPT_PATH)
assert SPEC and SPEC.loader
burn_grove = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(burn_grove)


def completed(command: list[str], returncode: int = 0, stdout: str = "", stderr: str = ""):
    return subprocess.CompletedProcess(command, returncode, stdout, stderr)


class IssueAndWorkspaceMatchingTests(unittest.TestCase):
    def test_parse_jira_key_requires_full_url(self):
        self.assertEqual(
            burn_grove.parse_issue_key(
                "https://example.atlassian.net/browse/we-123?x=1", "jira"
            ),
            "WE-123",
        )
        with self.assertRaisesRegex(burn_grove.BurnError, "full HTTP"):
            burn_grove.parse_issue_key("WE-123", "jira")

    def test_parse_linear_key_requires_linear_issue_url(self):
        self.assertEqual(
            burn_grove.parse_issue_key(
                "https://linear.app/writer/issue/asf-1/performance-reviews", "linear"
            ),
            "ASF-1",
        )
        with self.assertRaisesRegex(burn_grove.BurnError, "linear.app host"):
            burn_grove.parse_issue_key("https://example.com/issue/ASF-1", "linear")
        with self.assertRaisesRegex(burn_grove.BurnError, "issue key"):
            burn_grove.parse_issue_key("https://linear.app/writer/ASF-1", "linear")
        with self.assertRaisesRegex(burn_grove.BurnError, "use --linear-url"):
            burn_grove.parse_issue_key(
                "https://linear.app/writer/issue/ASF-1", "jira"
            )

    def test_workspace_matching_uses_provider_and_ref(self):
        workspaces = [
            {"name": "WE-123", "source": {"provider": "github", "ref": "WE-123"}},
            {"name": "unrelated", "source": {"provider": "jira", "ref": "we-123"}},
        ]
        self.assertEqual(
            burn_grove.find_workspace(workspaces, "jira", "WE-123")["name"],
            "unrelated",
        )

        linear = [{"name": "linear", "source": {"provider": "linear", "ref": "asf-1"}}]
        self.assertEqual(
            burn_grove.find_workspace(linear, "linear", "ASF-1")["name"], "linear"
        )

    def test_workspace_matching_refuses_missing_and_ambiguous_matches(self):
        with self.assertRaisesRegex(burn_grove.BurnError, "no Grove workspace"):
            burn_grove.find_workspace([], "jira", "WE-123")
        duplicate = {"source": {"provider": "jira", "ref": "WE-123"}}
        with self.assertRaisesRegex(burn_grove.BurnError, "found 2"):
            burn_grove.find_workspace([duplicate, duplicate], "jira", "WE-123")


class PathAndTabMatchingTests(unittest.TestCase):
    def test_path_containment_rejects_prefix_collision_and_relative_paths(self):
        root = Path("/tmp/grove/workspace")
        self.assertTrue(burn_grove.is_path_within("/tmp/grove/workspace/repo", root))
        self.assertTrue(burn_grove.is_path_within("/tmp/grove/workspace", root))
        self.assertFalse(burn_grove.is_path_within("/tmp/grove/workspace-other", root))
        self.assertFalse(burn_grove.is_path_within("repo", root))

    def test_absolute_path_rejects_root_and_relative_paths(self):
        with self.assertRaisesRegex(burn_grove.BurnError, "must be absolute"):
            burn_grove.absolute_path("relative", label="path")
        with self.assertRaisesRegex(burn_grove.BurnError, "filesystem root"):
            burn_grove.absolute_path("/", label="path")

    def test_tab_requires_exact_label_and_contained_pane_path(self):
        root = Path("/tmp/grove/workspace")
        tabs = [
            {"tab_id": "exact", "label": "workspace"},
            {"tab_id": "wrong-label", "label": "workspace-extra"},
            {"tab_id": "wrong-path", "label": "workspace"},
            {"tab_id": "foreground", "label": "workspace"},
        ]
        panes = [
            {"tab_id": "exact", "cwd": "/tmp/grove/workspace/repo"},
            {"tab_id": "wrong-label", "cwd": "/tmp/grove/workspace"},
            {"tab_id": "wrong-path", "cwd": "/tmp/grove/workspace-other"},
            {"tab_id": "foreground", "cwd": "/tmp", "foreground_cwd": "/tmp/grove/workspace"},
        ]
        self.assertEqual(
            burn_grove.find_associated_tabs("workspace", root, tabs, panes),
            ["exact", "foreground"],
        )


class RepositoryInspectionTests(unittest.TestCase):
    def test_dirty_and_untracked_files_are_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            clean = root / "clean"
            dirty = root / "dirty"
            clean.mkdir()
            dirty.mkdir()
            runner = Mock(
                side_effect=[
                    completed([], stdout=""),
                    completed([], stdout=" M tracked.py\n?? untracked.txt\n"),
                ]
            )
            statuses = burn_grove.inspect_repositories(
                [
                    {"repo_name": "clean", "worktree_path": str(clean)},
                    {"repo_name": "dirty", "worktree_path": str(dirty)},
                ],
                root,
                runner,
            )
            self.assertEqual(statuses[0][2], [])
            self.assertEqual(statuses[1][2], [" M tracked.py", "?? untracked.txt"])
            self.assertIn("--untracked-files=all", runner.call_args_list[1].args[0])

    def test_repo_outside_workspace_is_rejected_before_git(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            outside = root.parent / "outside"
            runner = Mock()
            with self.assertRaisesRegex(burn_grove.BurnError, "escapes"):
                burn_grove.inspect_repositories(
                    [{"repo_name": "bad", "worktree_path": str(outside)}], root, runner
                )
            runner.assert_not_called()

    def test_git_status_failure_is_a_hard_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            repo = root / "repo"
            repo.mkdir()
            runner = Mock(return_value=completed([], returncode=2, stderr="not a worktree"))
            with self.assertRaisesRegex(burn_grove.BurnError, "not a worktree"):
                burn_grove.inspect_repositories(
                    [{"repo_name": "repo", "worktree_path": str(repo)}], root, runner
                )


class CleanupFailureTests(unittest.TestCase):
    def test_close_failure_aborts_delete_but_attempts_every_close(self):
        runner = Mock(
            side_effect=[
                completed([], returncode=1, stderr="busy"),
                completed([]),
            ]
        )
        with self.assertRaisesRegex(burn_grove.BurnError, "workspace was not deleted"):
            burn_grove.cleanup("workspace", ["tab-1", "tab-2"], runner)
        self.assertEqual(runner.call_count, 2)
        self.assertNotIn(["gw", "delete", "workspace", "--force"], [call.args[0] for call in runner.call_args_list])

    def test_delete_failure_reports_partial_cleanup(self):
        runner = Mock(
            side_effect=[
                completed([]),
                completed([], returncode=1, stderr="delete failed"),
            ]
        )
        with self.assertRaisesRegex(burn_grove.BurnError, "tabs were closed.*deletion failed"):
            burn_grove.cleanup("workspace", ["tab-1"], runner)
        self.assertEqual(runner.call_args_list[-1].args[0], ["gw", "delete", "workspace", "--force"])

    def test_success_closes_all_tabs_before_forced_delete(self):
        runner = Mock(return_value=completed([]))
        burn_grove.cleanup("workspace", ["tab-1", "tab-2"], runner)
        self.assertEqual(
            [call.args[0] for call in runner.call_args_list],
            [
                ["herdr", "tab", "close", "tab-1"],
                ["herdr", "tab", "close", "tab-2"],
                ["gw", "delete", "workspace", "--force"],
            ],
        )


class AutomaticCleanupTests(unittest.TestCase):
    def test_clean_workspace_is_cleaned_automatically(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            repo = root / "repo"
            repo.mkdir()
            commands = []

            def runner(command):
                commands.append(command)
                if command == ["gw", "ws", "list", "--json"]:
                    payload = [
                        {
                            "name": "workspace",
                            "path": str(root),
                            "source": {"provider": "jira", "ref": "WE-123"},
                            "repos": [{"repo_name": "repo", "worktree_path": str(repo)}],
                        }
                    ]
                elif command == ["herdr", "workspace", "list"]:
                    payload = {"result": {"workspaces": [{"workspace_id": "w1"}]}}
                elif command == ["herdr", "tab", "list", "--workspace", "w1"]:
                    payload = {"result": {"tabs": [{"tab_id": "w1:t1", "label": "workspace"}]}}
                elif command == ["herdr", "pane", "list", "--workspace", "w1"]:
                    payload = {
                        "result": {
                            "panes": [{"tab_id": "w1:t1", "cwd": str(root)}]
                        }
                    }
                elif command[:3] == ["git", "-C", str(repo)]:
                    return completed(command)
                elif command == ["herdr", "tab", "close", "w1:t1"]:
                    return completed(command)
                elif command == ["gw", "delete", "workspace", "--force"]:
                    return completed(command)
                else:
                    self.fail(f"unexpected command: {command}")
                return completed(command, stdout=json.dumps(payload))

            output = io.StringIO()
            self.assertTrue(
                burn_grove.burn(
                    "https://example.atlassian.net/browse/WE-123",
                    "jira",
                    runner=runner,
                    output=output,
                )
            )
            self.assertIn("repo: clean", output.getvalue())
            self.assertNotIn("Delete this workspace?", output.getvalue())
            self.assertIn(["herdr", "tab", "close", "w1:t1"], commands)
            self.assertIn(["gw", "delete", "workspace", "--force"], commands)


if __name__ == "__main__":
    unittest.main()
