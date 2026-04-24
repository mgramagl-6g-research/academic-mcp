from typing import List, Dict, Any, Optional
from datetime import datetime
import requests
import os
from PyPDF2 import PdfReader
from loguru import logger
import urllib.parse

from ..types import Paper, PaperSource

class WOSSearcher(PaperSource):
    """Searcher for Web of Science papers using Expanded API.

    Note: Requires API key from Clarivate Analytics
    Set environment variable: WOS_API_KEY
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get('WOS_API_KEY', '')
        if not self.api_key:
            logger.warning("Web of Science API key not set. Set WOS_API_KEY environment variable.")

    def search(self, query: str, max_results: int = 10) -> List[Paper]:
        """Search Web of Science for papers"""
        if not self.api_key:
            logger.error("API key required for Web of Science search")
            return []

        try:
            import re
            # Web of Science requires field tags. If none is provided, default to Topic Search (TS)
            if not re.match(r'^[A-Z]{2}=', query.strip()):
                query = f"TS=({query})"

            params = {
                'databaseId': 'WOS',
                'usrQuery': query,
                'count': min(max_results, 100),
                'firstRecord': 1
            }
            response = requests.get(
                url='https://api.clarivate.com/api/wos/',
                params=params,
                headers={'X-ApiKey': self.api_key},
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
            papers = []
            records = data.get('Data', {}).get('Records', {}).get('records', {}).get('REC', [])
            if not isinstance(records, list):
                records = [records]

            for rec in records:
                try:
                    uid = rec.get('UID', '')
                    static_data = rec.get('static_data', {})
                    summary = static_data.get('summary', {})
                    item = static_data.get('item', {})
                    
                    titles_list = summary.get('titles', {}).get('title', [])
                    if not isinstance(titles_list, list):
                        titles_list = [titles_list]
                    
                    title = next((t.get('content', '') for t in titles_list if t.get('type') == 'item'), '')
                    if not title and titles_list:
                        title = titles_list[0].get('content', '')
                    
                    names_list = summary.get('names', {}).get('name', [])
                    if not isinstance(names_list, list):
                        names_list = [names_list]
                    authors = [n.get('full_name', '') or n.get('display_name', '') for n in names_list]
                    
                    pub_info = summary.get('pub_info', {})
                    pub_year = pub_info.get('pubyear', '')
                    published_date = datetime(int(pub_year), 1, 1) if pub_year else datetime.now()

                    dynamic_data = rec.get('dynamic_data', {})
                    cluster_related = dynamic_data.get('cluster_related', {})
                    identifiers_list = cluster_related.get('identifiers', {}).get('identifier', [])
                    if not isinstance(identifiers_list, list):
                        identifiers_list = [identifiers_list]
                    doi = next((i.get('value', '') for i in identifiers_list if i.get('type') == 'doi'), '')

                    fullrecord_metadata = static_data.get('fullrecord_metadata', {})
                    abstracts_list = fullrecord_metadata.get('abstracts', {}).get('abstract', {}).get('abstract_text', {}).get('p', [])
                    if not isinstance(abstracts_list, list):
                        abstracts_list = [abstracts_list]
                    abstract = " ".join(abstracts_list) if abstracts_list else ""

                    url = f"https://www.webofscience.com/wos/woscc/full-record/{uid}"
                    
                    paper = Paper(
                        paper_id=uid,
                        title=title,
                        authors=authors,
                        abstract=abstract,
                        doi=doi,
                        published_date=published_date,
                        pdf_url='',
                        url=url,
                        source='wos'
                    )
                    papers.append(paper)
                except Exception as e:
                    logger.error(f"Error parsing Web of Science entry: {e}")
                    continue

            return papers
        except Exception as e:
            logger.error(f"Error searching Web of Science: {e}")
            return []

    def download_pdf(self, paper_id: str, save_path: str) -> str:
        """Download PDF from Web of Science
        Note: The API generally does not provide direct PDF links without institutional proxy setup.
        """
        logger.warning("Web of Science Expanded API usually does not provide direct full-text PDF links.")
        raise NotImplementedError("Web of Science PDF download requires institutional access or proxy integration.")

    def read_paper(self, paper_id: str, save_path: str = "./downloads") -> str:
        pdf_path = os.path.join(save_path, f"{paper_id}.pdf")
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF not found: {pdf_path}. Web of Science requires institutional access to download PDF.")

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
    searcher = WOSSearcher()
    print("Testing search functionality...")
    query = "TS=(machine learning)"
    papers = searcher.search(query, max_results=5)
    for i, p in enumerate(papers, 1):
        print(f"{i}. {p.title} (ID: {p.paper_id})")
