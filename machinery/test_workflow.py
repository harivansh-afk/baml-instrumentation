"""Hand-computed state transitions, independent of all workload implementations."""

import json
import unittest

from fixtures import encode, oracle, fixture


class WorkflowOracle(unittest.TestCase):
    def config(self, requests, batch=None, retain=2):
        return encode(
            dict(
                requests=[encode(r) for r in requests],
                batch=len(requests) if batch is None else batch,
                retain=retain,
                fanout=1,
                delay_ms=0,
                capture=True,
            )
        )

    def request(self, key, mode="replace"):
        return dict(
            key=key, mode=mode, items=[dict(kind="credit", amount=2, payload=[3])]
        )

    def test_fifo_hit_does_not_refresh_eviction_position(self):
        requests = [
            self.request("a"),
            self.request("b"),
            self.request("a", "accumulate"),
            self.request("c"),
        ]
        result = oracle("08_stateful_workflow", self.config(requests))
        self.assertEqual([r["total"] for r in result["responses"]], [6, 6, 12, 6])
        self.assertEqual(result["responses"][-1]["evicted"], "a")
        self.assertEqual([e["key"] for e in result["cache"]], ["b", "c"])

    def test_invalid_request_is_atomic_and_state_survives_calls(self):
        a = self.request("a", "accumulate")
        invalid = self.request("b") | {"mode": "invalid"}
        raw = self.config([a, invalid], batch=1, retain=1)
        result = oracle("08_stateful_workflow", raw, jobs=2, warmup=1)
        self.assertEqual(result["processed"], 3)
        self.assertEqual(result["cache"], [dict(key="a", total=12, check=6, count=1)])
        self.assertEqual(result["responses"][0]["seq"], 2)

    def test_retention_and_fanout_do_not_change_input_stream(self):
        a = json.loads(fixture("08_stateful_workflow", size=3, fanout=1, retain=4))
        b = json.loads(fixture("08_stateful_workflow", size=3, fanout=4, retain=64))
        self.assertEqual(a["requests"], b["requests"])
