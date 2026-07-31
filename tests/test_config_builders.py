import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "single"))

from relay_admin.config_builders import build_singbox_outbound, build_stream_settings
from relay_admin.share_links import parse_share_link


class ConfigBuilderTests(unittest.TestCase):
    def test_build_singbox_anytls_outbound(self):
        link = (
            "anytls://11111111-2222-3333-4444-555555555555@example.com:7001"
            "?security=tls&sni=example.com&fp=chrome&insecure=1&allowInsecure=1&type=tcp#demo"
        )
        node = parse_share_link(link, 11080)
        outbound = build_singbox_outbound(node)

        self.assertEqual(outbound["type"], "anytls")
        self.assertEqual(outbound["server"], "example.com")
        self.assertEqual(outbound["server_port"], 7001)
        self.assertEqual(outbound["password"], "11111111-2222-3333-4444-555555555555")
        self.assertTrue(outbound["tls"]["enabled"])
        self.assertEqual(outbound["tls"]["server_name"], "example.com")
        self.assertTrue(outbound["tls"]["insecure"])
        self.assertEqual(outbound["tls"]["utls"]["fingerprint"], "chrome")

    def test_build_singbox_vless_reality_outbound(self):
        link = (
            "vless://11111111-2222-3333-4444-555555555555@example.com:8443"
            "?encryption=none&flow=xtls-rprx-vision&security=reality&sni=www.speedtest.net"
            "&fp=chrome&pbk=public-key&sid=4053c105e3&spx=%2F&type=tcp&headerType=none#demo"
        )
        node = parse_share_link(link, 11080)
        outbound = build_singbox_outbound(node)

        self.assertEqual(outbound["type"], "vless")
        self.assertEqual(outbound["flow"], "xtls-rprx-vision")
        self.assertTrue(outbound["tls"]["enabled"])
        self.assertEqual(outbound["tls"]["server_name"], "www.speedtest.net")
        self.assertEqual(outbound["tls"]["reality"]["public_key"], "public-key")
        self.assertEqual(outbound["tls"]["reality"]["short_id"], "4053c105e3")
        self.assertEqual(outbound["tls"]["utls"]["fingerprint"], "chrome")

    def test_build_xray_vless_reality_stream_settings(self):
        link = (
            "vless://11111111-2222-3333-4444-555555555555@example.com:8443"
            "?encryption=none&flow=xtls-rprx-vision&security=reality&sni=www.speedtest.net"
            "&fp=chrome&pbk=public-key&sid=4053c105e3&spx=%2F&type=tcp&headerType=none#demo"
        )
        node = parse_share_link(link, 11080)
        stream = build_stream_settings(node)

        self.assertEqual(stream["security"], "reality")
        self.assertEqual(stream["realitySettings"]["serverName"], "www.speedtest.net")
        self.assertEqual(stream["realitySettings"]["publicKey"], "public-key")
        self.assertEqual(stream["realitySettings"]["shortId"], "4053c105e3")
        self.assertEqual(stream["realitySettings"]["spiderX"], "/")


if __name__ == "__main__":
    unittest.main()
