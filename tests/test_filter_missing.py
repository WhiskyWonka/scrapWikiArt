import unittest

import pandas as pd

from ScrapWikiArt.utils import filter_missing_descriptions


class TestFilterMissingDescriptions(unittest.TestCase):
    COLUMNS = ["Description", "WikiDescription"]

    def test_filters_nan(self):
        df = pd.DataFrame({"Description": [float("nan")], "WikiDescription": [float("nan")]})
        result = filter_missing_descriptions(df, self.COLUMNS)
        self.assertEqual(len(result), 1)

    def test_filters_empty_strings(self):
        df = pd.DataFrame({"Description": [""], "WikiDescription": [""]})
        result = filter_missing_descriptions(df, self.COLUMNS)
        self.assertEqual(len(result), 1)

    def test_filters_whitespace_only(self):
        df = pd.DataFrame({"Description": ["   "], "WikiDescription": ["\t"]})
        result = filter_missing_descriptions(df, self.COLUMNS)
        self.assertEqual(len(result), 1)

    def test_keeps_row_with_any_content(self):
        df = pd.DataFrame({"Description": ["Mona Lisa"], "WikiDescription": [""]})
        result = filter_missing_descriptions(df, self.COLUMNS)
        self.assertEqual(len(result), 0)

    def test_mixed_nan_and_empty(self):
        df = pd.DataFrame({"Description": [float("nan")], "WikiDescription": [""]})
        result = filter_missing_descriptions(df, self.COLUMNS)
        self.assertEqual(len(result), 1)

    def test_single_column_when_wikidescription_absent(self):
        df = pd.DataFrame({"Description": ["", "has text"]})
        result = filter_missing_descriptions(df, ["Description"])
        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["Description"], "")

    def test_and_logic_across_rows_and_columns(self):
        df = pd.DataFrame({
            "Description": ["Mona Lisa", float("nan"), "", "   "],
            "WikiDescription": [float("nan"), "", "some text", "   "],
        })
        result = filter_missing_descriptions(df, self.COLUMNS)
        self.assertEqual(len(result), 2)
        self.assertTrue(pd.isna(result.iloc[0]["Description"]))
        self.assertEqual(result.iloc[1]["Description"], "   ")


if __name__ == "__main__":
    unittest.main()
