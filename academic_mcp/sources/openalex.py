from typing import List, Dict, Any, Optional
from datetime import datetime
import requests
import os
from PyPDF2 import PdfReader
from loguru import logger

from ..types import Paper, PaperSource

class OpenAlexSearcher(PaperSource):
    """Searcher for OpenAlex papers.
    Uses https://api.openalex.org/works endpoint.
    Configuring OPENALEX_EMAIL environment variable allows usage of the polite pool.
    """

    def __init__(self, email: Optional[str] = None):
        self.email = email or os.environ.get('OPENALEX_EMAIL', '')

    def search(self, query: str, max_results: int = 10) -> List[Paper]:
        params = {
            'search': query,
            'per-page': min(max_results, 200)
        }
        if self.email:
            params['mailto'] = self.email

        try:
            response = requests.get(
                url='https://api.openalex.org/works',
                params=params,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()

            papers = []
            for item in data.get('results', []):
                try:
                    paper_id = item.get('id', '')
                    if paper_id.startswith('https://openalex.org/'):
                        paper_id = paper_id.replace('https://openalex.org/', '')
                        
                    title = item.get('title') or ''
                    
                    authors = []
                    for authorship in item.get('authorships', []):
                        author = authorship.get('author', {})
                        if author.get('display_name'):
                            authors.append(author['display_name'])
                    
                    pub_date_str = item.get('publication_date', '')
                    if pub_date_str:
                        try:
                            published_date = datetime.strptime(pub_date_str, '%Y-%m-%d')
                        except ValueError:
                            published_date = datetime.now()
                    else:
                        published_date = datetime.now()

                    doi = item.get('doi', '')
                    if doi and doi.startswith('https://doi.org/'):
                        doi = doi.replace('https://doi.org/', '')

                    # Reconstruct abstract from inverted index
                    abstract = ""
                    inverted_index = item.get('abstract_inverted_index', {})
                    if inverted_index:
                        # Find the maximum index to determine the array size
                        max_idx = -1
                        for term, indices in inverted_index.items():
                            if indices:
                                max_idx = max(max_idx, max(indices))
                        if max_idx >= 0:
                            words = [""] * (max_idx + 1)
                            for term, indices in inverted_index.items():
                                for idx in indices:
                                    words[idx] = term
                            abstract = " ".join(words).strip()

                    primary_location = item.get('primary_location', {}) or {}
                    pdf_url = primary_location.get('pdf_url', '')
                    url = primary_location.get('landing_page_url', '')
                    if not url:
                        url = item.get('id', '')

                    paper = Paper(
                        paper_id=paper_id,
                        title=title,
                        authors=authors,
                        abstract=abstract,
                        doi=doi,
                        published_date=published_date,
                        pdf_url=pdf_url or '',
                        url=url or '',
                        source='openalex'
                    )
                    papers.append(paper)
                except Exception as e:
                    logger.error(f"Error parsing OpenAlex entry: {e}")
                    continue

            return papers
        except Exception as e:
            logger.error(f"Error searching OpenAlex: {e}")
            return []

    def download_pdf(self, paper_id: str, save_path: str) -> str:
        """Download PDF from OpenAlex's provided pdf_url"""
        params = {}
        if self.email:
            params['mailto'] = self.email

        # Re-fetch the item to get the pdf_url if needed
        work_url = f'https://api.openalex.org/works/{paper_id}'
        try:
            response = requests.get(work_url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            primary_location = data.get('primary_location', {}) or {}
            pdf_url = primary_location.get('pdf_url', '')
            
            if not pdf_url:
                raise ValueError(f"No PDF URL found for OpenAlex paper {paper_id}")
            
            os.makedirs(save_path, exist_ok=True)
            pdf_response = requests.get(pdf_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=60)
            pdf_response.raise_for_status()
            
            output_file = os.path.join(save_path, f"{paper_id}.pdf")
            with open(output_file, 'wb') as f:
                f.write(pdf_response.content)
            
            return output_file
        except Exception as e:
            logger.error(f"Error downloading PDF for {paper_id}: {e}")
            raise

    def read_paper(self, paper_id: str, save_path: str = "./downloads") -> str:
        pdf_path = os.path.join(save_path, f"{paper_id}.pdf")
        if not os.path.exists(pdf_path):
            pdf_path = self.download_pdf(paper_id, save_path)
            
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
    searcher = OpenAlexSearcher()
    print("Testing search functionality...")
    query = "machine learning"
    try:
        papers = searcher.search(query, max_results=5)
        print(f"Found {len(papers)} papers for query '{query}':")
        for i, paper in enumerate(papers, 1):
            print(f"{i}. {paper.title} (ID: {paper.paper_id})")
    except Exception as e:
        print(f"Error during search: {e}")
