import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "single"))

from relay_admin import services


class ServiceTests(unittest.TestCase):
    def test_parse_share_links_supports_multiline(self):
        links = services.parse_share_links(
            "\n vless://123e4567-e89b-12d3-a456-426614174000@example.com:443?type=ws#demo-1 \n\n"
            "trojan://password@example.com:443?type=ws#demo-2 \n"
        )
        self.assertEqual(len(links), 2)
        self.assertTrue(links[0].startswith("vless://"))
        self.assertTrue(links[1].startswith("trojan://"))

    def test_parse_local_port_uses_fallback(self):
        self.assertEqual(services.parse_local_port("", fallback=11080), 11080)

    def test_parse_local_port_rejects_invalid_range(self):
        with self.assertRaisesRegex(ValueError, "1 到 65535"):
            services.parse_local_port("70000")

    def test_import_node_uses_next_port_and_persists(self):
        form = {
            "local_port": [""],
            "share_link": ["vless://123e4567-e89b-12d3-a456-426614174000@example.com:443?type=ws#demo"],
            "name_override": [""],
            "kernel": ["xray"],
        }
        with patch("relay_admin.services.load_nodes", return_value=[]), patch(
            "relay_admin.services.persist_and_reload"
        ) as persist:
            message = services.import_node(form)
        self.assertIn("已导入节点", message)
        persist.assert_called_once()

    def test_import_node_supports_multiline_batch(self):
        form = {
            "local_port": ["11080"],
            "share_link": [
                "vless://123e4567-e89b-12d3-a456-426614174000@example.com:443?type=ws#demo-1\n"
                "vless://123e4567-e89b-12d3-a456-426614174000@example.com:443?type=ws#demo-2"
            ],
            "name_override": [""],
            "kernel": ["xray"],
        }
        existing = [{"id": "existing", "local_port": 11081}]
        with patch("relay_admin.services.load_nodes", return_value=existing), patch(
            "relay_admin.services.persist_and_reload"
        ) as persist:
            message = services.import_node(form)

        self.assertIn("已批量导入 2 个节点", message)
        persist.assert_called_once()
        persisted_nodes = persist.call_args.args[0]
        self.assertEqual([node["local_port"] for node in persisted_nodes[1:]], [11080, 11082])

    def test_import_node_rejects_name_override_in_batch_mode(self):
        form = {
            "local_port": ["11080"],
            "share_link": [
                "vless://123e4567-e89b-12d3-a456-426614174000@example.com:443?type=ws#demo-1\n"
                "vless://123e4567-e89b-12d3-a456-426614174000@example.com:443?type=ws#demo-2"
            ],
            "name_override": ["same-name"],
            "kernel": ["xray"],
        }
        with patch("relay_admin.services.load_nodes", return_value=[]):
            with self.assertRaisesRegex(ValueError, "批量导入时不支持统一节点名称"):
                services.import_node(form)


if __name__ == "__main__":
    unittest.main()
