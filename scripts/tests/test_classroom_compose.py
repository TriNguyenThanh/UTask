"""Validate the Classroom gateway boundary."""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class ClassroomComposeTests(unittest.TestCase):
    def test_gateway_blocks_both_internal_paths_before_public_preflight(self):
        nginx = (ROOT / "infra/nginx/nginx.conf").read_text()
        for route in (
            "location = /api/classroom/internal {",
            "location ^~ /api/classroom/internal/ {",
        ):
            self.assertIn(route + "\n      return 404;", nginx)
        public = nginx.split("location /api/classroom/ {", 1)[1].split("\n    }", 1)[0]
        self.assertIn("if ($request_method = OPTIONS) { return 204; }", public)
        self.assertIn("rewrite ^/api/classroom/(.*)$ /$1 break;", public)

