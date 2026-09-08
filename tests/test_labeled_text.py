import unittest

from ScrapWikiArt.utils import labeled_text


class TestLabeledText(unittest.TestCase):
    def test_none_input(self):
        self.assertIsNone(labeled_text(None))

    def test_removes_s_label_and_whitespace(self):
        raw = "<li>\n            <s>Original Title:</s>\n            Mona Lisa\n        </li>"
        self.assertEqual(labeled_text(raw), "Mona Lisa")

    def test_removes_s_label_with_class(self):
        raw = '<li>\n            <s class="title">Dimensions:</s>\n            77 x 53 cm\n        </li>'
        self.assertEqual(labeled_text(raw), "77 x 53 cm")

    def test_robust_to_minified_html(self):
        raw = "<li><s>Original Title:</s>The Last Supper</li>"
        self.assertEqual(labeled_text(raw), "The Last Supper")

    def test_handles_multiple_s_labels(self):
        raw = "<li><s>First:</s><s>Second:</s>value</li>"
        self.assertEqual(labeled_text(raw), "value")

    def test_text_with_nested_elements(self):
        raw = "<li><s>Country:</s><a href='/x'>France</a></li>"
        self.assertEqual(labeled_text(raw), "France")

    def test_empty_s_tag(self):
        raw = "<li><s></s>value</li>"
        self.assertEqual(labeled_text(raw), "value")

    def test_label_only_no_value(self):
        raw = "<li><s>Original Title:</s></li>"
        self.assertEqual(labeled_text(raw), "")


if __name__ == "__main__":
    unittest.main()
