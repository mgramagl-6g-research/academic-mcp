from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime
import requests
import os
from PyPDF2 import PdfReader
from loguru import logger
import urllib.parse

from ..types import Paper, PaperSource


@dataclass
class WOSReference:
    """Lightweight representation of a cited reference from the WoS /references endpoint.

    This endpoint returns a different schema than full WoS records — it provides
    basic bibliographic info about each cited reference rather than a full REC.
    """
    uid: str
    cited_author: str
    cited_work: str
    cited_title: str
    year: Optional[int]
    doi: str
    times_cited: int
    page: Optional[str]

class WOSSearcher(PaperSource):
    """Searcher for Web of Science papers using Expanded API.

    Note: Requires API key from Clarivate Analytics
    Set environment variable: WOS_API_KEY
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get('WOS_API_KEY', '')
        if not self.api_key:
            logger.warning("Web of Science API key not set. Set WOS_API_KEY environment variable.")

    # ------------------------------------------------------------------ #
    #  Internal helpers                                                    #
    # ------------------------------------------------------------------ #

    def _headers(self) -> Dict[str, str]:
        return {'X-ApiKey': self.api_key}

    @staticmethod
    def _parse_record(rec: Dict[str, Any]) -> Paper:
        """Parse a single WoS REC dict into a Paper."""
        uid = rec.get('UID', '')
        static_data = rec.get('static_data', {})
        summary = static_data.get('summary', {})

        # Title
        titles_list = summary.get('titles', {}).get('title', [])
        if not isinstance(titles_list, list):
            titles_list = [titles_list]
        title = next((t.get('content', '') for t in titles_list if t.get('type') == 'item'), '')
        if not title and titles_list:
            title = titles_list[0].get('content', '')

        # Authors
        names_list = summary.get('names', {}).get('name', [])
        if not isinstance(names_list, list):
            names_list = [names_list]
        authors = [n.get('full_name', '') or n.get('display_name', '') for n in names_list]

        # Publication year
        pub_info = summary.get('pub_info', {})
        pub_year = pub_info.get('pubyear', '')
        published_date = datetime(int(pub_year), 1, 1) if pub_year else datetime.now()

        # DOI from dynamic_data identifiers
        dynamic_data = rec.get('dynamic_data', {})
        cluster_related = dynamic_data.get('cluster_related', {})
        identifiers_list = cluster_related.get('identifiers', {}).get('identifier', [])
        if not isinstance(identifiers_list, list):
            identifiers_list = [identifiers_list]
        doi = next((i.get('value', '') for i in identifiers_list if i.get('type') == 'doi'), '')

        # Abstract
        fullrecord_metadata = static_data.get('fullrecord_metadata', {})
        abstracts_list = fullrecord_metadata.get('abstracts', {}).get('abstract', {}).get('abstract_text', {}).get('p', [])
        if not isinstance(abstracts_list, list):
            abstracts_list = [abstracts_list]
        abstract = " ".join(str(a) for a in abstracts_list) if abstracts_list else ""

        # Times-cited (from the first silo_tc entry for WOS)
        citation_related = dynamic_data.get('citation_related', {})
        tc_list = citation_related.get('tc_list', {}).get('silo_tc', [])
        if not isinstance(tc_list, list):
            tc_list = [tc_list]
        times_cited = 0
        for tc in tc_list:
            if tc.get('coll_id') == 'WOS':
                times_cited = int(tc.get('local_count', 0))
                break

        url = f"https://www.webofscience.com/wos/woscc/full-record/{uid}"

        return Paper(
            paper_id=uid,
            title=title,
            authors=authors,
            abstract=abstract,
            doi=doi,
            published_date=published_date,
            pdf_url='',
            url=url,
            source='wos',
            citations=times_cited,
        )

    def _extract_papers_from_response(self, data: Dict[str, Any]) -> List[Paper]:
        """Extract Paper list from a standard WoS search/citing/related response."""
        records = data.get('Data', {}).get('Records', {}).get('records', {}).get('REC', [])
        if not isinstance(records, list):
            records = [records]

        papers: List[Paper] = []
        for rec in records:
            try:
                papers.append(self._parse_record(rec))
            except Exception as e:
                logger.error(f"Error parsing Web of Science entry: {e}")
                continue
        return papers

    # ------------------------------------------------------------------ #
    #  Search                                                              #
    # ------------------------------------------------------------------ #

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
                url='https://wos-api.clarivate.com/api/wos/',
                params=params,
                headers=self._headers(),
                timeout=30
            )
            response.raise_for_status()
            return self._extract_papers_from_response(response.json())
        except Exception as e:
            logger.error(f"Error searching Web of Science: {e}")
            return []

    # ------------------------------------------------------------------ #
    #  Citing articles  (GET /citing)                                      #
    # ------------------------------------------------------------------ #

    def citing_articles(self, unique_id: str, max_results: int = 10,
                        publish_time_span: Optional[str] = None,
                        sort_field: Optional[str] = None) -> List[Paper]:
        """Find articles that cite the paper identified by *unique_id*.

        Args:
            unique_id: WoS UID, e.g. ``WOS:000270372400005``.
            max_results: Number of citing records to return (1-100).
            publish_time_span: Optional date range ``yyyy-mm-dd+yyyy-mm-dd``.
            sort_field: Optional sort, e.g. ``TC+D`` (times cited descending).

        Returns:
            List of Paper objects representing citing articles.
        """
        if not self.api_key:
            logger.error("API key required for Web of Science citing articles lookup")
            return []

        try:
            params: Dict[str, Any] = {
                'databaseId': 'WOS',
                'uniqueId': unique_id,
                'count': min(max_results, 100),
                'firstRecord': 1,
            }
            if publish_time_span:
                params['publishTimeSpan'] = publish_time_span
            if sort_field:
                params['sortField'] = sort_field

            response = requests.get(
                url='https://wos-api.clarivate.com/api/wos/citing',
                params=params,
                headers=self._headers(),
                timeout=30,
            )
            response.raise_for_status()
            return self._extract_papers_from_response(response.json())
        except Exception as e:
            logger.error(f"Error fetching WoS citing articles for {unique_id}: {e}")
            return []

    # ------------------------------------------------------------------ #
    #  Cited references  (GET /references)                                 #
    # ------------------------------------------------------------------ #

    def references(self, unique_id: str, max_results: int = 10,
                   sort_field: Optional[str] = None) -> List[WOSReference]:
        """Return the cited references of the paper identified by *unique_id*.

        The /references endpoint returns a *different* schema from the
        standard search endpoint — each entry is a lightweight reference
        record, not a full WoS REC.

        Args:
            unique_id: WoS UID, e.g. ``WOS:000270372400005``.
            max_results: Number of references to return (1-100).
            sort_field: Optional sort string.

        Returns:
            List of ``WOSReference`` dataclass instances.
        """
        if not self.api_key:
            logger.error("API key required for Web of Science references lookup")
            return []

        try:
            params: Dict[str, Any] = {
                'databaseId': 'WOS',
                'uniqueId': unique_id,
                'count': min(max_results, 100),
                'firstRecord': 1,
            }
            if sort_field:
                params['sortField'] = sort_field

            response = requests.get(
                url='https://wos-api.clarivate.com/api/wos/references',
                params=params,
                headers=self._headers(),
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

            refs_data = data.get('Data', [])
            if not isinstance(refs_data, list):
                refs_data = [refs_data]

            refs: List[WOSReference] = []
            for entry in refs_data:
                try:
                    year_val = entry.get('year')
                    refs.append(WOSReference(
                        uid=entry.get('UID', ''),
                        cited_author=entry.get('citedAuthor', ''),
                        cited_work=entry.get('citedWork', ''),
                        cited_title=entry.get('citedTitle', ''),
                        year=int(year_val) if year_val else None,
                        doi=entry.get('doi', ''),
                        times_cited=int(entry.get('timesCited', 0)),
                        page=str(entry.get('page', '')) if entry.get('page') else None,
                    ))
                except Exception as e:
                    logger.error(f"Error parsing WoS reference entry: {e}")
                    continue
            return refs
        except Exception as e:
            logger.error(f"Error fetching WoS references for {unique_id}: {e}")
            return []

    # ------------------------------------------------------------------ #
    #  Related records  (GET /related)                                     #
    # ------------------------------------------------------------------ #

    def related_records(self, unique_id: str, max_results: int = 10,
                        publish_time_span: Optional[str] = None,
                        sort_field: Optional[str] = None) -> List[Paper]:
        """Find records related to *unique_id* (they share cited references).

        Args:
            unique_id: WoS UID, e.g. ``WOS:000270372400005``.
            max_results: Number of related records to return (1-100).
            publish_time_span: Optional date range ``yyyy-mm-dd+yyyy-mm-dd``.
            sort_field: Optional sort string.

        Returns:
            List of Paper objects representing related records.
        """
        if not self.api_key:
            logger.error("API key required for Web of Science related records lookup")
            return []

        try:
            params: Dict[str, Any] = {
                'databaseId': 'WOS',
                'uniqueId': unique_id,
                'count': min(max_results, 100),
                'firstRecord': 1,
            }
            if publish_time_span:
                params['publishTimeSpan'] = publish_time_span
            if sort_field:
                params['sortField'] = sort_field

            response = requests.get(
                url='https://wos-api.clarivate.com/api/wos/related',
                params=params,
                headers=self._headers(),
                timeout=30,
            )
            response.raise_for_status()
            return self._extract_papers_from_response(response.json())
        except Exception as e:
            logger.error(f"Error fetching WoS related records for {unique_id}: {e}")
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

    if papers:
        uid = papers[0].paper_id
        print(f"\nTesting citing articles for {uid}...")
        citing = searcher.citing_articles(uid, max_results=3)
        for i, p in enumerate(citing, 1):
            print(f"  {i}. {p.title} (cited {p.citations} times)")

        print(f"\nTesting references for {uid}...")
        refs = searcher.references(uid, max_results=3)
        for i, r in enumerate(refs, 1):
            print(f"  {i}. {r.cited_author} — {r.cited_title} ({r.year}) doi:{r.doi}")

        print(f"\nTesting related records for {uid}...")
        related = searcher.related_records(uid, max_results=3)
        for i, p in enumerate(related, 1):
            print(f"  {i}. {p.title} (ID: {p.paper_id})")
