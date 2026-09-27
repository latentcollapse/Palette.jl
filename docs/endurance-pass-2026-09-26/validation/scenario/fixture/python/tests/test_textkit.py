import json, unittest
from pathlib import Path
import textkit

CASES = json.loads((Path(__file__).parent / "cases.json").read_text())


class GoldenCases(unittest.TestCase):
    def test_cases(self):
        for i, (fn, args, kwargs, expected) in enumerate(CASES):
            with self.subTest(i=i, fn=fn, args=args, kwargs=kwargs):
                self.assertEqual(getattr(textkit, fn)(*args, **kwargs), expected)


if __name__ == "__main__":
    unittest.main()
