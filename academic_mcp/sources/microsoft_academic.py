from typing import List, Dict, Any, Optional
from datetime import datetime
import requests
import os
from PyPDF2 import PdfReader
from loguru import logger

from ..types import Paper, PaperSource


class MicrosoftAcademicSearcher(PaperSource):
    """Searcher for Microsoft Academic papers

    Note: Microsoft Academic was retired on December 31, 2021
    This implementation is a placeholder for historical reference
    """

    def search(self, query: str, max_results: int = 10) -> List[Paper]:
        """Search Microsoft Academic for papers

        Note: Microsoft Academic was retired on December 31, 2021
        """
        logger.warning("Microsoft Academic was retired on December 31, 2021")
        logger.warning("Please use alternative sources like Semantic Scholar")
        logger.info("Data available at: https://www.microsoft.com/en-us/research/project/microsoft-academic-graph/")
        return []

    def download_pdf(self, paper_id: str, save_path: str) -> str:
        """Download PDF from Microsoft Academic

        Note: Microsoft Academic was retired
        """
        logger.warning("Microsoft Academic was retired on December 31, 2021")
        raise NotImplementedError("Microsoft Academic service is no longer available")

    def read_paper(self, paper_id: str, save_path: str = "./downloads") -> str:
        """Read a paper and convert it to text format"""
        pdf_path = os.path.join(save_path, f"{paper_id}.pdf")

        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF not found: {pdf_path}. Microsoft Academic is no longer available.")

        # Read the PDF
        try:
            reader = PdfReader(pdf_path)
            text = ""

            for page in reader.pages:
                text += page.extract_text() + "\n"

            return text.strip()
        except Exception as e:
            logger.error(f"Error reading PDF for {paper_id}: {e}")
            return ""


if __name__ == "__main__":
    # Test MicrosoftAcademicSearcher
    searcher = MicrosoftAcademicSearcher()

    # Test search
    print("Testing search functionality...")
    query = "machine learning"
    max_results = 5
    try:
        papers = searcher.search(query, max_results=max_results)
        print(f"Found {len(papers)} papers for query '{query}':")
        for i, paper in enumerate(papers, 1):
            print(f"{i}. {paper.title} (ID: {paper.paper_id})")
    except Exception as e:
        print(f"Error during search: {e}")
