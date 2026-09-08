import unittest

from ScrapWikiArt.utils import pipe_join


class TestPipeJoin(unittest.TestCase):
    def test_empty_iterable(self):
        self.assertEqual(pipe_join([]), "")

    def test_none_iterable(self):
        self.assertEqual(pipe_join(None), "")

    def test_single_value(self):
        self.assertEqual(pipe_join(["Cubism"]), "Cubism")

    def test_multiple_values(self):
        self.assertEqual(pipe_join(["a", "b", "c"]), "a | b | c")

    def test_none_values_skipped(self):
        self.assertEqual(pipe_join(["a", None, "c"]), "a | c")

    def test_empty_strings_skipped(self):
        self.assertEqual(pipe_join(["a", "", "c"]), "a | c")

    def test_all_none(self):
        self.assertEqual(pipe_join([None, None]), "")

    def test_all_empty(self):
        self.assertEqual(pipe_join(["", ""]), "")

    def test_leading_none(self):
        self.assertEqual(pipe_join([None, "b", "c"]), "b | c")

    def test_trailing_none(self):
        self.assertEqual(pipe_join(["a", "b", None]), "a | b")


if __name__ == "__main__":
    unittest.main()
