"""Static ingress contract; these checks do not simulate Nginx realip behavior."""

import ipaddress
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Snapshot of the official Cloudflare lists, checked on 2026-10-19.
# https://www.cloudflare.com/ips-v4 https://www.cloudflare.com/ips-v6
CLOUDFLARE_CIDRS = {
    "173.245.48.0/20",
    "103.21.244.0/22",
    "103.22.200.0/22",
    "103.31.4.0/22",
    "141.101.64.0/18",
    "108.162.192.0/18",
    "190.93.240.0/20",
    "188.114.96.0/20",
    "197.234.240.0/22",
    "198.41.128.0/17",
    "162.158.0.0/15",
    "104.16.0.0/13",
    "104.24.0.0/14",
    "172.64.0.0/13",
    "131.0.72.0/22",
    "2400:cb00::/32",
    "2606:4700::/32",
    "2803:f800::/32",
    "2405:b500::/32",
    "2405:8100::/32",
    "2a06:98c0::/29",
    "2c0f:f248::/32",
}


class ClientIPIngressTests(unittest.TestCase):
    def setUp(self):
        source = (ROOT / "infra/nginx/nginx.conf").read_text(encoding="utf-8")
        self.nginx = re.sub(r"#.*", "", source)

    def test_only_official_cloudflare_ipv4_and_ipv6_peers_are_trusted(self):
        ranges = re.findall(r"\bset_real_ip_from\s+([^;]+);", self.nginx)
        self.assertEqual(set(ranges), CLOUDFLARE_CIDRS)
        self.assertEqual(len(ranges), len(CLOUDFLARE_CIDRS))
        networks = [ipaddress.ip_network(value, strict=True) for value in ranges]
        self.assertEqual({network.version for network in networks}, {4, 6})
        for peer in ("127.0.0.1", "172.18.0.1", "198.51.100.7", "::1", "2001:db8::7"):
            with self.subTest(untrusted_peer=peer):
                self.assertFalse(
                    any(ipaddress.ip_address(peer) in network for network in networks)
                )

    def test_realip_uses_single_cloudflare_header_at_http_scope(self):
        self.assertEqual(
            re.findall(r"\breal_ip_header\s+([^;]+);", self.nginx),
            ["CF-Connecting-IP"],
        )
        self.assertEqual(
            re.findall(r"\breal_ip_recursive\s+([^;]+);", self.nginx), ["off"]
        )
        # Trust and canonical headers must apply to every service location;
        # a location-level proxy_set_header would disable parent inheritance.
        http_defaults, server = self.nginx.split("  server {", 1)
        self.assertIn("real_ip_header CF-Connecting-IP;", http_defaults)
        self.assertNotIn("proxy_set_header", server)
        self.assertNotIn("set_real_ip_from", server)

    def test_forwarding_headers_replace_forged_values_instead_of_appending(self):
        for header in ("X-Real-IP", "X-Forwarded-For"):
            with self.subTest(header=header):
                self.assertEqual(
                    re.findall(
                        rf"\bproxy_set_header\s+{header}\s+([^;]+);",
                        self.nginx,
                        flags=re.IGNORECASE,
                    ),
                    ["$remote_addr"],
                )
        self.assertNotIn("$proxy_add_x_forwarded_for", self.nginx)
        self.assertNotRegex(self.nginx, r"\$http_(x_real_ip|x_forwarded_for)")

    def test_cors_allows_only_staging_web_and_local_origins_with_credentials(self):
        map_body = self.nginx.split('map "$host|$http_origin" $cors_origin {', 1)[1]
        map_body = map_body.split("}", 1)[0]
        self.assertIn('default "";', map_body)
        self.assertIn(
            '"utask-api.u-code.dev|https://utask.u-code.dev" $http_origin;', map_body
        )
        self.assertNotIn("*", map_body)
        self.assertNotIn("null", map_body)
        self.assertIn(
            'add_header Access-Control-Allow-Origin $cors_origin always;', self.nginx
        )
        self.assertIn(
            'add_header Access-Control-Allow-Credentials "true" always;', self.nginx
        )
        self.assertIn('add_header Vary "Origin" always;', self.nginx)
        self.assertIn('if ($request_method = OPTIONS) { return 204; }', self.nginx)

    def test_identity_docker_mapping_has_overridable_bridge_default(self):
        source = (ROOT / "infra/env/identity-service.env").read_text(encoding="utf-8")
        values = re.findall(
            r"^IDENTITY_TRUSTED_PROXY_CIDRS=(.*)$", source, re.MULTILINE
        )
        self.assertEqual(values, ["${IDENTITY_TRUSTED_PROXY_CIDRS:-172.16.0.0/12}"])
        # Standard deployment must work without an extra operator-facing IP setting.
        template = (ROOT / ".env.example").read_text(encoding="utf-8")
        self.assertNotRegex(template, r"(?m)^IDENTITY_TRUSTED_PROXY_CIDRS=")
        # Both entrypoints must consume this mapping, without overriding it.
        for name in ("docker-compose.yml", "docker-compose.staging.yml"):
            with self.subTest(compose=name):
                compose = (ROOT / name).read_text(encoding="utf-8")
                self.assertIn("./infra/env/identity-service.env", compose)
                self.assertNotIn("IDENTITY_TRUSTED_PROXY_CIDRS", compose)


if __name__ == "__main__":
    unittest.main()
