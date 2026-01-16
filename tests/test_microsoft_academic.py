# tests/test_microsoft_academic.py
import unittest
from academic_mcp.sources.microsoft_academic import MicrosoftAcademicSearcher


class TestMicrosoftAcademicSearcher(unittest.TestCase):
    def test_search(self):
        """Test Microsoft Academic search (service retired)"""
        searcher = MicrosoftAcademicSearcher()
        papers = searcher.search("machine learning", max_results=5)
        print("Microsoft Academic was retired on December 31, 2021")
        print("Please use alternative sources like Semantic Scholar")
        # Expected to return empty list
        self.assertEqual(len(papers), 0)


if __name__ == '__main__':
    unittest.main()
