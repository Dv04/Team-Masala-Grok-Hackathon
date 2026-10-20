"""Fail the build if dev1 names another model provider or its API host."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _needles():
    # Split so this file does not itself contain the banned substrings.
    return (
        "gp" + "t-",
        "clau" + "de",
        "gemi" + "ni",
        "anthro" + "pic",
        "api.open" + "ai.com",
    )


class ProviderLockTests(unittest.TestCase):
    def test_dev1_mentions_only_xai(self):
        hits = []
        for path in ROOT.rglob("*"):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore").lower()
            for needle in _needles():
                if needle in text:
                    hits.append(f"{path.relative_to(ROOT)}: {needle}")
        self.assertEqual(hits, [], "other providers mentioned:\n" + "\n".join(hits))


if __name__ == "__main__":
    unittest.main()
