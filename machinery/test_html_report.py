"""Protect the report's comparison boundaries and unit conversions."""

from copy import deepcopy
from unittest import TestCase, mock

import html_report as report


class ReportTests(TestCase):
    def test_batch_average_excludes_failed_and_missing_observations(self):
        rows = [
            {
                "status": "ok",
                "language": "baml",
                "jobs": "4",
                "execution_wall_ns": "12000",
            },
            {
                "status": "ok",
                "language": "baml",
                "jobs": "2",
                "execution_wall_ns": "10000",
            },
            {
                "status": "failed",
                "language": "baml",
                "jobs": "1",
                "execution_wall_ns": "900000",
            },
            {"status": "ok", "language": "baml", "jobs": "4", "execution_wall_ns": ""},
        ]
        result = report.metric_stats(rows, report.METRICS[0])
        self.assertEqual(result["values"], [3.0, 5.0])
        self.assertEqual((result["n"], result["median"]), (2, 4.0))
        self.assertIsNone(report.stats([]))

    def test_missing_counter_is_not_zero(self):
        metric = next(m for m in report.METRICS if m[0] == "gc_execution")
        base = {"status": "ok", "language": "baml", "jobs": "8"}
        self.assertIsNone(report.metric_stats([base | {"gc_execution": ""}], metric))
        self.assertEqual(
            report.metric_stats([base | {"gc_execution": "0"}], metric)["median"], 0
        )

    def test_collection_rejects_mixed_artifact_and_duplicate_trial(self):
        root = report.ROOT / "measurements/2026-09-29-shared-host"
        original = report.read_csv
        rows = original(root / "runtime.csv")
        first = rows[0]
        peer = next(
            i
            for i, row in enumerate(rows[1:], 1)
            if row["scenario"] == first["scenario"]
            and report.config(row) == report.config(first)
        )
        for kind in ("artifact", "duplicate"):
            modified = deepcopy(rows)
            if kind == "artifact":
                modified[peer]["artifact_sha256"] = "different-artifact"
            else:
                modified.append(modified[0])
            with (
                self.subTest(kind=kind),
                mock.patch.object(
                    report,
                    "read_csv",
                    side_effect=lambda path: (
                        modified if path.name == "runtime.csv" else original(path)
                    ),
                ),
                self.assertRaises(ValueError),
            ):
                report.collect(root)

    def test_http_rejects_mixed_request_identity(self):
        rows = [
            {
                "trial_path": "a",
                "scenario": "hello",
                "language": "baml",
                "level": "off",
                "status": "ok",
                "artifact_sha256": "same",
                "input_sha256": "one",
                "requests": "300",
                "offered_rate": "100",
            },
            {
                "trial_path": "b",
                "scenario": "hello",
                "language": "baml",
                "level": "off",
                "status": "ok",
                "artifact_sha256": "same",
                "input_sha256": "two",
                "requests": "300",
                "offered_rate": "100",
            },
        ]
        with (
            mock.patch.object(report, "read_csv", return_value=rows),
            self.assertRaisesRegex(ValueError, "Mixed HTTP input_sha256"),
        ):
            report.http_rows(report.ROOT)

    def test_http_rejects_duplicate_trial(self):
        row = {
            "trial_path": "a",
            "scenario": "hello",
            "language": "baml",
            "level": "off",
            "status": "ok",
        }
        with (
            mock.patch.object(report, "read_csv", return_value=[row, row]),
            self.assertRaisesRegex(ValueError, "Duplicate HTTP trial"),
        ):
            report.http_rows(report.ROOT)

    def test_http_failures_and_schedule_exclusions_stay_distinct(self):
        base = {
            "status": "ok",
            "client_schedule_valid": "True",
            "client_lag_p99_ns": "500000",
            "failed": "0",
        }
        timeout = base | {"status": "request_failure", "failed": "5"}
        bad_schedule = base | {
            "client_schedule_valid": "False",
            "client_lag_p99_ns": "20000000",
        }
        bad_recording = base | {"status": "telemetry_coverage_failure"}
        self.assertTrue(report.http_metric_eligible(timeout, "throughput"))
        for row in (bad_schedule, bad_recording):
            self.assertFalse(report.http_metric_eligible(row, "throughput"))
            self.assertTrue(report.http_metric_eligible(row, "client_lag_p99_ns"))
            self.assertTrue(report.http_metric_eligible(row, "failed"))

    def test_versions_come_from_selected_cases_only(self):
        manifest = {
            "selected/baml": {"language": "baml", "version": "new"},
            "unselected/baml": {"language": "baml", "version": "old"},
        }
        self.assertEqual(
            report.versions_for_cases(manifest, ["selected"]), {"baml": "new"}
        )
        with self.assertRaisesRegex(ValueError, "Mixed baml versions"):
            report.versions_for_cases(manifest, ["selected", "unselected"])
