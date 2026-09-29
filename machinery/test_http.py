"""Exercise the real response decoder and arrival schedule without benchmark data."""

import asyncio
import importlib.util
from pathlib import Path
import time
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "http_driver", Path(__file__).parent / "http/client.py"
)
client = importlib.util.module_from_spec(spec)
spec.loader.exec_module(client)


class ClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_length_chunked_and_invalid_response(self):
        responses = [
            b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 7\r\n\r\n{"v":1}',
            b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nTransfer-Encoding: chunked\r\n\r\n7\r\n{"v":1}\r\n0\r\n\r\n',
            b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 10\r\n\r\n{"v":true}',
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n",
        ]

        async def serve(reader, writer):
            await reader.readuntil(b"\r\n\r\n")
            writer.write(responses.pop(0))
            await writer.drain()
            writer.close()
            await writer.wait_closed()

        server = await asyncio.start_server(serve, "127.0.0.1", 0)
        async with server:
            address = server.sockets[0].getsockname()
            outcomes = [
                await client.request(address, "GET", "/", "", {"v": 1})
                for _ in range(4)
            ]
        self.assertEqual(
            [r["status"] for r in outcomes], ["ok", "ok", "wrong_response", "error"]
        )
        self.assertTrue(all(r["completed_ns"] >= r["dispatch_ns"] for r in outcomes))

    async def test_arrivals_do_not_wait_for_previous_completion(self):
        async def slow(*args, **kwargs):
            start = time.monotonic_ns()
            await asyncio.sleep(0.04)
            return dict(
                status="ok", dispatch_ns=start, completed_ns=time.monotonic_ns()
            )

        config = dict(
            port=0,
            method="GET",
            path="/",
            body="",
            expected={},
            deadline_s=1,
            rate=1000,
            requests=12,
            max_inflight=2,
        )
        with patch.object(client, "request", side_effect=slow):
            result = await client.run(config)
        self.assertEqual(len(result["requests"]), 12)
        self.assertEqual([r["index"] for r in result["requests"]], list(range(12)))
        self.assertGreater(result["failed"], 0)
        self.assertTrue(
            any(r["status"] == "client_capacity_rejected" for r in result["requests"])
        )
        for r in result["requests"]:
            if r["status"] == "ok":
                self.assertEqual(r["latency_ns"], r["service_ns"] + r["lag_ns"])

    def test_nearest_rank_percentile_and_missing(self):
        self.assertIsNone(client.percentile([], 0.99))
        self.assertEqual(client.percentile(list(range(1, 21)), 0.95), 19)
        self.assertEqual(client.percentile(list(range(1, 21)), 0.99), 20)
