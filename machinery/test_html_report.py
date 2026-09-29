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
