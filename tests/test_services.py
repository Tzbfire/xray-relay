import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "single"))

from relay_admin import services


class ServiceTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
