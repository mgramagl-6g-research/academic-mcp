from typing import List, Dict, Any, Optional
from datetime import datetime
import requests
import os
from PyPDF2 import PdfReader
from loguru import logger

from ..types import Paper, PaperSource

class UnpaywallSearcher(PaperSource):
    """Source for Unpaywall.
    Note: Unpaywall does not provide search capabilities by keywords, only resolution by DOI.
    It acts as a downloader for papers given a DOI as the paper_id.
    Requires UNPAYWALL_EMAIL environment variable.
    """

    def __init__(self, email: Optional[str] = None):
        self.email = email or os.environ.get('UNPAYWALL_EMAIL', '')
        if not self.email:
            logger.warning("Unpaywall API requires an email address. Set UNPAYWALL_EMAIL environment variable.")

    def search(self, query: str, max_results: int = 10) -> List[Paper]:
        """Search is not supported by Unpaywall"""
        logger.warning("Unpaywall does not support keyword search. Please use download_pdf with a DOI.")
        return []

    def download_pdf(self, paper_id: str, save_path: str) -> str:
        """Download PDF using Unpaywall given a DOI (paper_id)"""
        if not self.email:
            raise ValueError("Email required for Unpaywall API. Set UNPAYWALL_EMAIL environment variable.")

        # Ensure paper_id is a DOI without the prefix if it exists
        doi = paper_id
        if doi.startswith('https://doi.org/'):
            doi = doi.replace('https://doi.org/', '')
        elif doi.startswith('doi:'):
            doi = doi.replace('doi:', '')

        url = f"https://api.unpaywall.org/v2/{doi}"
        params = {'email': self.email}

        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            best_oa_location = data.get('best_oa_location')
            if not best_oa_location:
                raise ValueError(f"No open access location found for DOI {doi} via Unpaywall.")

            pdf_url = best_oa_location.get('url_for_pdf')
            if not pdf_url:
                raise ValueError(f"No PDF URL available for DOI {doi} via Unpaywall.")

            os.makedirs(save_path, exist_ok=True)
            pdf_response = requests.get(pdf_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=60)
            pdf_response.raise_for_status()

            # Sanitize DOI for filename
            safe_doi = doi.replace('/', '_').replace(':', '_')
            output_file = os.path.join(save_path, f"{safe_doi}.pdf")
            with open(output_file, 'wb') as f:
                f.write(pdf_response.content)

            return output_file

        except Exception as e:
            logger.error(f"Error downloading PDF via Unpaywall for {doi}: {e}")
            raise

    def read_paper(self, paper_id: str, save_path: str = "./downloads") -> str:
        doi = paper_id
        if doi.startswith('https://doi.org/'):
            doi = doi.replace('https://doi.org/', '')
        elif doi.startswith('doi:'):
            doi = doi.replace('doi:', '')
        safe_doi = doi.replace('/', '_').replace(':', '_')
        pdf_path = os.path.join(save_path, f"{safe_doi}.pdf")

        if not os.path.exists(pdf_path):
            pdf_path = self.download_pdf(paper_id, save_path)

        try:
            reader = PdfReader(pdf_path)
            text = ""
            for page in reader.pages:
                text += page.extract_text() + "\n"
            return text.strip()
        except Exception as e:
            logger.error(f"Error reading PDF via Unpaywall for {paper_id}: {e}")
            return ""

if __name__ == "__main__":
    searcher = UnpaywallSearcher()
    # Test Unpaywall using a well known OA DOI
    doi = "10.1038/nature12373"
    try:
        if searcher.email:
            print(f"Attempting to resolve DOI: {doi} via Unpaywall")
            print("Note: Skipping actual download test to avoid writing files in test block.")
        else:
            print("No email set, skipping Unpaywall test.")
    except Exception as e:
        print(f"Error: {e}")
