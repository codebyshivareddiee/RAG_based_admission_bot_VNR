"""
Simple webpage content fetcher for fallback web search.
"""

from __future__ import annotations

import logging
import re
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from html.parser import HTMLParser

logger = logging.getLogger(__name__)


class HTMLTextExtractor(HTMLParser):
    """Extract clean text content from HTML."""
    
    def __init__(self):
        super().__init__()
        self.text_parts = []
        self.skip_tags = {'script', 'style', 'head', 'meta', 'link', 'noscript'}
        self.current_tag = None
    
    def handle_starttag(self, tag, attrs):
        self.current_tag = tag
    
    def handle_endtag(self, tag):
        self.current_tag = None
    
    def handle_data(self, data):
        if self.current_tag not in self.skip_tags:
            cleaned = data.strip()
            if cleaned:
                self.text_parts.append(cleaned)
    
    def get_text(self) -> str:
        """Return extracted text joined with spaces."""
        return ' '.join(self.text_parts)


def fetch_webpage_content(url: str, timeout: int = 10) -> str:
    """
    Fetch webpage content and extract clean text.
    
    Args:
        url: URL to fetch
        timeout: Request timeout in seconds
    
    Returns:
        Extracted text content from webpage
    
    Raises:
        Exception: If fetch fails
    """
    try:
        # Create request with user agent to avoid blocking
        headers = {
            'User-Agent': 'VNRVJIET-AdmissionBot/1.0 (Educational chatbot)'
        }
        req = Request(url, headers=headers)
        
        logger.info(f"Fetching webpage: {url}")
        
        # Fetch webpage
        with urlopen(req, timeout=timeout) as response:
            if response.status != 200:
                raise Exception(f"HTTP {response.status}")
            
            # Read and decode content
            html_content = response.read().decode('utf-8', errors='ignore')
        
        # Extract text from HTML
        parser = HTMLTextExtractor()
        parser.feed(html_content)
        text_content = parser.get_text()
        
        # Clean up extracted text
        # Remove multiple spaces
        text_content = re.sub(r'\s+', ' ', text_content)
        
        # Remove common footer/header noise patterns
        text_content = re.sub(r'(Home|About|Contact|Login|Sign Up|Privacy Policy)+', ' ', text_content)
        
        logger.info(f"Extracted {len(text_content)} characters from webpage")
        
        if not text_content or len(text_content) < 100:
            raise Exception("Insufficient content extracted from webpage")
        
        return text_content.strip()
    
    except HTTPError as e:
        logger.error(f"HTTP error fetching {url}: {e.code} {e.reason}")
        raise Exception(f"Failed to fetch webpage: HTTP {e.code}")
    
    except URLError as e:
        logger.error(f"URL error fetching {url}: {e.reason}")
        raise Exception(f"Failed to connect to website: {e.reason}")
    
    except Exception as e:
        logger.error(f"Error fetching webpage {url}: {e}")
        raise Exception(f"Failed to fetch webpage: {str(e)}")
