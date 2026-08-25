from __future__ import annotations

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "summon_grove.py"
SPEC = importlib.util.spec_from_file_location("summon_grove", SCRIPT_PATH)
assert SPEC and SPEC.loader
summon_grove = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = summon_grove
SPEC.loader.exec_module(summon_grove)


class IssueUrlTests(unittest.TestCase):
    def test_parse_jira_issue_url(self):
        self.assertEqual(
            summon_grove.parse_issue_key(
                "https://example.atlassian.net/browse/we-123?x=1", "jira"
            ),
            "WE-123",
        )

    def test_parse_linear_issue_url_with_optional_slug(self):
        self.assertEqual(
            summon_grove.parse_issue_key(
                "https://linear.app/writer/issue/asf-1/performance-reviews", "linear"
            ),
            "ASF-1",
        )

    def test_reject_non_linear_host(self):
        with self.assertRaisesRegex(SystemExit, "linear.app host"):
            summon_grove.parse_issue_key("https://example.com/issue/ASF-1", "linear")

    def test_reject_linear_url_under_jira_flag(self):
        with self.assertRaisesRegex(SystemExit, "use --linear-url"):
            summon_grove.parse_issue_key(
                "https://linear.app/writer/issue/ASF-1", "jira"
            )


class WorkspaceMetadataTests(unittest.TestCase):
    @patch.object(summon_grove, "workspace_path", return_value="/tmp/asf-1")
    @patch.object(summon_grove, "run")
    def test_linear_workspace_records_linear_source(self, run, _workspace_path):
        run.return_value = subprocess.CompletedProcess([], 0, "", "")

        summon_grove.create_workspace(
            workspace="asf-1-title",
            branch="asf-1-title",
            preset="backend",
            provider="linear",
            issue_url="https://linear.app/writer/issue/ASF-1/title",
            issue_key="ASF-1",
            title="ASF-1: Title",
        )

        command = run.call_args.args[0]
        self.assertEqual(command[command.index("--source-provider") + 1], "linear")
        self.assertEqual(command[command.index("--source-ref") + 1], "ASF-1")


class ParserTests(unittest.TestCase):
    def test_requires_exactly_one_provider_url(self):
        parser = summon_grove.build_parser()
        jira = parser.parse_args(
            ["--jira-url", "https://example.atlassian.net/browse/WE-123", "--preset", "backend"]
        )
        self.assertEqual(summon_grove.issue_source(jira)[0], "jira")

        linear = parser.parse_args(
            ["--linear-url", "https://linear.app/writer/issue/ASF-1", "--preset", "backend"]
        )
        self.assertEqual(summon_grove.issue_source(linear)[0], "linear")

        with self.assertRaises(SystemExit):
            parser.parse_args(["--preset", "backend"])
        with self.assertRaises(SystemExit):
            parser.parse_args(
                [
                    "--jira-url",
                    "https://example.atlassian.net/browse/WE-123",
                    "--linear-url",
                    "https://linear.app/writer/issue/ASF-1",
                    "--preset",
                    "backend",
                ]
            )


if __name__ == "__main__":
    unittest.main()
