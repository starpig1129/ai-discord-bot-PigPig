"""Webpage fetching tools for LLM integration.

This module provides a LangChain-compatible tool for fetching and extracting
text content from a given URL using aiohttp and BeautifulSoup.
"""

from typing import TYPE_CHECKING
import aiohttp
from bs4 import BeautifulSoup
from langchain_core.tools import tool

from addons.logging import get_logger
from function import func

if TYPE_CHECKING:
    from llm.schema import OrchestratorRequest

_logger = get_logger(server_id="Bot", source="llm.tools.fetch_webpage")

class FetchWebpageTools:
    """Container class for webpage fetching tools."""

    def __init__(self, runtime: "OrchestratorRequest"):
        self.runtime = runtime
        self.logger = getattr(self.runtime, "logger", _logger)

    def get_tools(self) -> list:
        runtime = self.runtime

        @tool
        async def fetch_webpage(url: str) -> str:
            """Fetches and extracts the main text content from a given URL.

            Use this tool when you need to read the contents of a specific webpage,
            such as when a user asks you to summarize an article or extract information
            from a link they provided.

            Args:
                url: The full HTTP/HTTPS URL to fetch.

            Returns:
                The extracted text content from the webpage, truncated to a reasonable
                length if it's too large, or an error message if the fetch fails.
            """
            logger = getattr(runtime, "logger", _logger)
            logger.info("Tool 'fetch_webpage' called", extra={"url": url})

            try:
                timeout = aiohttp.ClientTimeout(total=15.0)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    headers = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
                    }
                    async with session.get(url, headers=headers) as response:
                        response.raise_for_status()

                        content_type = response.headers.get('Content-Type', '').lower()
                        if 'text/html' not in content_type and 'text/plain' not in content_type:
                            return f"Error: URL points to a non-text resource (Content-Type: {content_type}). This tool only supports HTML or plain text."

                        html = await response.text()

                        # Parse HTML and extract text
                        soup = BeautifulSoup(html, 'html.parser')

                        # Remove script and style elements
                        for script in soup(["script", "style", "noscript", "meta", "link", "header", "footer", "nav"]):
                            script.decompose()

                        text = soup.get_text(separator=' ', strip=True)

                        # Clean up multiple spaces and newlines
                        lines = (line.strip() for line in text.splitlines())
                        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
                        text = '\n'.join(chunk for chunk in chunks if chunk)

                        # Truncate to avoid context overflow (approx 10000 chars)
                        max_chars = 10000
                        if len(text) > max_chars:
                            text = text[:max_chars] + "... [Content truncated]"

                        return text if text else "Successfully fetched page, but no text content was found."

            except aiohttp.ClientError as e:
                return f"Failed to fetch webpage due to a network or client error: {str(e)}"
            except Exception as e:
                await func.report_error(e, f"fetch_webpage tool failed for URL '{url}'")
                return f"An unexpected error occurred while fetching the webpage: {str(e)}"

        return [fetch_webpage]
