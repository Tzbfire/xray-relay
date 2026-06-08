import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "single"))

from relay_admin.nodes import next_port, validate_kernel_for_node


class NodeRulesTests(unittest.TestCase):
    def test_next_port_skips_used_ports(self):
        nodes = [
            {"local_port": 11080},
            {"local_port": 11081},
            {"local_port": 11083},
        ]
        self.assertEqual(next_port(nodes), 11082)

    def test_hysteria2_only_allows_singbox(self):
        node = {"protocol": "hysteria2", "kernel": "xray"}
        with self.assertRaisesRegex(ValueError, "仅支持内核"):
            validate_kernel_for_node(node)

    def test_anytls_only_allows_singbox(self):
        node = {"protocol": "anytls", "kernel": "xray"}
        with self.assertRaisesRegex(ValueError, "仅支持内核"):
            validate_kernel_for_node(node)


if __name__ == "__main__":
    unittest.main()
