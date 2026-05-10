"""News summary clients.

A news client returns a short, recent, market-moving summary string for
a symbol. The interface is intentionally narrow (a single
``latest_news_summary(symbol) -> str``) so the rest of the scanner is
agnostic about which vendor is fetching the news.

Three clients ship today:

* :class:`GeminiNewsClient` — uses Gemini with Google Search grounding.
  This is the default because the project already requires a Gemini key
  for the analyst layer, so news incurs no additional vendor.
* :class:`PerplexityNewsClient` — original ``sonar``-based client; kept
  for users who already have Perplexity API credits.
* :class:`NoNewsClient` — explicit no-op when news is disabled.

:func:`build_news_client` resolves ``settings.news_source`` to one of
these. Unknown values log and fall back to "none", matching the posture
of the provider/strategy factories.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - import cycle guard
    from swing_scanner.config import Settings
from swing_scanner.http_client import HttpRequestError, post_json


SUPPORTED_NEWS_SOURCES = ("gemini", "perplexity", "none")
DEFAULT_NEWS_SOURCE = "gemini"


class NewsClient:
    """Minimal protocol for news clients."""

    def latest_news_summary(self, symbol: str) -> str:  # pragma: no cover
        raise NotImplementedError


class NoNewsClient(NewsClient):
    """No-op client used when ``NEWS_SOURCE=none``."""

    def latest_news_summary(self, symbol: str) -> str:
        return ""


class GeminiNewsClient(NewsClient):
    """News summaries via Gemini + Google Search grounding.

    Uses the ``google_search`` tool (Gemini 2.5 family) so the model can
    pull live web context and cite recent stories rather than relying on
    its training cutoff.
    """

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash"):
        self.api_key = api_key
        self.model = model

    def latest_news_summary(self, symbol: str) -> str:
        if not self.api_key:
            return "No news API key configured."

        endpoint = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent"
        )
        prompt = (
            "You cover Indian equities listed on the NSE. Provide a concise "
            f"(<=3 sentences) summary of the most recent material market-moving "
            f"news for the company with ticker {symbol}, from the last few "
            "trading days. Prioritise: earnings, guidance, broker rating "
            "changes, M&A, regulatory or SEBI actions, sector-moving events "
            "(Nifty IT, Bank Nifty, sector indices), block deals, and "
            "FII/DII flow context if relevant. Exclude routine corporate "
            "filings such as ESOP/ESPS allotments, board minor changes, "
            "and dividend record-date intimations. Use neutral, factual "
            "language; no recommendations. If nothing material has been "
            "reported, say so explicitly."
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "tools": [{"google_search": {}}],
            "generationConfig": {"temperature": 0.2},
        }
        try:
            raw = post_json(
                endpoint,
                payload=payload,
                headers={"x-goog-api-key": self.api_key},
            )
            return raw["candidates"][0]["content"]["parts"][0]["text"].strip()
        except HttpRequestError:
            return "Unable to fetch news summary."


class PerplexityNewsClient(NewsClient):
    """News summaries via Perplexity ``sonar``. Requires API credits."""

    def __init__(self, api_key: str, model: str = "sonar"):
        self.api_key = api_key
        self.model = model

    def latest_news_summary(self, symbol: str) -> str:
        if not self.api_key:
            return "No news API key configured."
        url = "https://api.perplexity.ai/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": f"Provide a concise latest market-moving news summary for {symbol}.",
                }
            ],
            "temperature": 0.2,
        }
        try:
            data = post_json(
                url,
                payload=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            return data["choices"][0]["message"]["content"]
        except HttpRequestError:
            return "Unable to fetch news summary."


def build_news_client(settings: "Settings") -> NewsClient:
    """Resolve ``settings.news_source`` to a concrete :class:`NewsClient`."""
    name = (settings.news_source or DEFAULT_NEWS_SOURCE).strip().lower()
    if name not in SUPPORTED_NEWS_SOURCES:
        print(
            f"Unknown NEWS_SOURCE={name!r}; falling back to 'none'. "
            f"Supported: {', '.join(SUPPORTED_NEWS_SOURCES)}."
        )
        name = "none"

    if name == "gemini":
        return GeminiNewsClient(api_key=settings.gemini_api_key, model=settings.gemini_model)
    if name == "perplexity":
        return PerplexityNewsClient(api_key=settings.perplexity_api_key)
    return NoNewsClient()
