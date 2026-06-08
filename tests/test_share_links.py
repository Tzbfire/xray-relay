import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "single"))

from relay_admin.share_links import parse_share_link


class ShareLinkTests(unittest.TestCase):
    def test_parse_vless_link(self):
        link = "vless://123e4567-e89b-12d3-a456-426614174000@example.com:443?type=ws&security=tls&path=%2Fws#demo"
        node = parse_share_link(link, 11080)
        self.assertEqual(node["protocol"], "vless")
        self.assertEqual(node["address"], "example.com")
        self.assertEqual(node["port"], 443)
        self.assertEqual(node["uuid"], "123e4567-e89b-12d3-a456-426614174000")
        self.assertEqual(node["network"], "ws")

    def test_unknown_scheme_raises(self):
        with self.assertRaisesRegex(ValueError, "当前只支持"):
            parse_share_link("http://example.com", 11080)

    def test_parse_anytls_link(self):
        link = (
            "anytls://11111111-2222-3333-4444-555555555555@example.com:7001"
            "?security=tls&sni=example.com&fp=chrome&insecure=1"
            "&allowInsecure=1&type=tcp#2x%E4%B8%93%E7%BA%BF-%E6%96%B0%E5%8A%A0%E5%9D%A1-1"
        )
        node = parse_share_link(link, 11080)
        self.assertEqual(node["protocol"], "anytls")
        self.assertEqual(node["kernel"], "sing-box")
        self.assertEqual(node["address"], "example.com")
        self.assertEqual(node["port"], 7001)
        self.assertEqual(node["password"], "11111111-2222-3333-4444-555555555555")
        self.assertEqual(node["sni"], "example.com")
        self.assertEqual(node["fingerprint"], "chrome")
        self.assertTrue(node["allow_insecure"])
        self.assertEqual(node["name"], "2x专线-新加坡-1")


if __name__ == "__main__":
    unittest.main()
