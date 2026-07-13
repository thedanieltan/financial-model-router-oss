from __future__ import annotations

import unittest

from fmr.cli import build_parser


class ServeCommandTests(unittest.TestCase):
    def test_serve_defaults_to_loopback(self) -> None:
        args = build_parser().parse_args(["serve"])
        self.assertEqual(args.host, "127.0.0.1")
        self.assertEqual(args.port, 8000)
        self.assertFalse(args.reload)

    def test_serve_allows_explicit_host_and_port(self) -> None:
        args = build_parser().parse_args(
            ["serve", "--host", "0.0.0.0", "--port", "9000", "--reload"]
        )
        self.assertEqual(args.host, "0.0.0.0")
        self.assertEqual(args.port, 9000)
        self.assertTrue(args.reload)


if __name__ == "__main__":
    unittest.main()
