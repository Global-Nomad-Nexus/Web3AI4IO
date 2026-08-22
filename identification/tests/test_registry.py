from pathlib import Path
import unittest

from web3io_identification.registry import load_registry, summarize_gate


ROOT = Path(__file__).resolve().parents[1]


class RegistryTest(unittest.TestCase):
    def test_current_registry_is_valid(self) -> None:
        rows = load_registry(ROOT / "event_registry.csv")
        self.assertEqual(len(rows), 4)

    def test_staggered_gate_is_currently_closed(self) -> None:
        rows = load_registry(ROOT / "event_registry.csv")
        summary = summarize_gate(rows)
        self.assertFalse(summary.staggered_gate_passes)
        self.assertEqual(summary.accepted_events, 0)


if __name__ == "__main__":
    unittest.main()
