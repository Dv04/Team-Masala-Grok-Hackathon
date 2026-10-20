"""Fail if this tree names another model provider."""
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _needles():
    # Pieces are split so this file does not contain the banned spellings.
    return (
        "gp" + "t-",
        "cl" + "aude",
        "gem" + "ini",
        "anth" + "ropic",
        "api.ope" + "nai.com",
    )


class GrokOnlyTests(unittest.TestCase):
    def test_marketing_tree_is_xai_only(self):
        needles = _needles()
        hits = []
        for dirpath, dirnames, filenames in os.walk(ROOT):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for name in filenames:
                path = os.path.join(dirpath, name)
                try:
                    with open(path, encoding="utf-8", errors="replace") as fh:
                        text = fh.read().lower()
                except OSError:
                    continue
                for needle in needles:
                    if needle in text:
                        hits.append(f"{os.path.relpath(path, ROOT)}: {needle}")
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
