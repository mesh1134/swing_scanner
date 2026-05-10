"""LLM-based trade analyst layer.

Runs **after** the deterministic strategy filter — only candidates that
already passed ``Strategy.analyze(...)`` reach this module. The LLM is
used as an explanation layer for momentum/trend/volume/quality/risk
commentary; trade levels (entry / target / stop-loss) are computed
deterministically from the :class:`SetupSignal` and the Bollinger lower
band so the model never invents prices.

The structured :class:`TradeAnalysis` object is the wire format. It
carries both numeric trade levels and per-axis commentary, plus a
``features`` dict that mirrors what was sent to the LLM. This makes the
same payload usable for Telegram today, FastAPI tomorrow, and a mobile
client without further reshaping.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any
from urllib import request

from swing_scanner.analysis import SetupSignal


# --- Deterministic level math --------------------------------------------------
# Three knobs control the stop:
#   * MIN_RISK_PCT  — floor: the stop will never be tighter than this.
#   * MAX_RISK_PCT  — ceiling: the stop will never be wider than this. Caps
#                     the bb-lower stop on setups in the upper half of the
#                     band, where bb-lower is far below price and would
#                     otherwise produce a position-trade-sized risk.
#   * EMA_STOP_BUFFER — distance below EMA20 to use as the trend stop.
MIN_RISK_PCT = 0.02         # 2.0% — floor on stop distance. Raised from
                            # 1.5% on 2026-05-10 after observing 5 of 16
                            # NSE symbols hitting the old floor — too tight
                            # for a swing trade where typical noise alone
                            # would stop you out. Industry-standard swing
                            # risk is 3-6%; 2.0% is the conservative floor.
MAX_RISK_PCT = 0.04         # 4%   — ceiling on stop distance (swing trade).
EMA_STOP_BUFFER = 0.01      # 1%   — buffer below EMA20 for the trend stop.
TARGET_R_MULTIPLE = 1.8     # Reward : risk multiple for the target.

# --- LLM endpoint --------------------------------------------------------------
# Endpoint template; the model id is interpolated at call time so it
# stays driven by ``Settings.gemini_model`` (env: GEMINI_MODEL).
GEMINI_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "{model}:generateContent?key={api_key}"
)
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"


@dataclass
class TradeAnalysis:
    """Structured analyst output for a single candidate setup.

    Numeric fields are deterministic; commentary fields come from the
    LLM (or a rule-based fallback when the API key is missing or the
    call fails). ``features`` is the exact semantic payload sent to the
    model — preserved for downstream consumers (FastAPI / mobile) and
    for prompt-engineering observability.
    """

    symbol: str
    strategy_name: str
    direction: str
    entry: float
    target: float
    stop_loss: float
    risk_reward: float

    # LLM commentary (each field is a short analyst-style sentence).
    thesis: str
    momentum: str
    trend: str
    volume: str
    setup_quality: str
    risks: str

    # News context the analyst was given (may be empty).
    news_summary: str = ""

    # Mirror of the structured payload sent to the LLM. Keeps the wire
    # format JSON-serialisable for any future API surface.
    features: dict[str, Any] = field(default_factory=dict)

    # ``"llm"`` when commentary came from Gemini; ``"fallback"`` when it
    # was generated locally (no key / network error / parse failure).
    source: str = "llm"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Backward-compat aliases so any older imports keep resolving. Both the
# class name and the method name from the previous version stay valid.
TradeIdea = TradeAnalysis


# --- Helpers -------------------------------------------------------------------
def compute_trade_levels(signal: SetupSignal) -> tuple[float, float, float, float]:
    """Return ``(entry, target, stop_loss, risk_reward)`` from indicators.

    Considers three candidate stops and picks the one closest to entry
    (i.e. tightest), within the [MIN_RISK_PCT, MAX_RISK_PCT] band:

    * ``ema_stop``  — 1% below EMA20 (trend-following stop).
    * ``bb_stop``   — Bollinger lower band (mean-reversion stop).
    * ``pct_ceiling`` — 4% below entry (always-valid worst case).

    This avoids the failure mode where a setup in the upper half of the
    BB range gets a 10–20% stop just because bb-lower is far away.
    """
    entry = float(signal.close)
    ema = float(signal.ema_20)
    bb_l = float(signal.bb_lower)

    ema_stop = ema * (1 - EMA_STOP_BUFFER)
    bb_stop = bb_l
    pct_ceiling = entry * (1 - MAX_RISK_PCT)

    # Filter to stops strictly below entry, then take the tightest
    # (highest-priced). pct_ceiling is always valid, so the list is
    # never empty.
    candidates = [s for s in (ema_stop, bb_stop, pct_ceiling) if s < entry]
    stop = max(candidates) if candidates else entry * (1 - MIN_RISK_PCT)

    # Enforce the floor: a stop tighter than MIN_RISK_PCT gets relaxed.
    if entry - stop < entry * MIN_RISK_PCT:
        stop = entry * (1 - MIN_RISK_PCT)

    risk = entry - stop
    target = entry + (risk * TARGET_R_MULTIPLE)
    return round(entry, 2), round(target, 2), round(stop, 2), round(TARGET_R_MULTIPLE, 2)


def _derive_features(signal: SetupSignal, strategy_name: str) -> dict[str, Any]:
    """Reduce a :class:`SetupSignal` to a token-efficient semantic payload.

    Sends derived strings (not raw candle arrays) to the LLM so the
    prompt stays compact and the model has something interpretable to
    reason about. The deterministic candidate flag is intentionally
    NOT included — the strategy filter is upstream architecture and
    its output should not bias the qualitative analysis.
    """
    close = float(signal.close)
    ema = float(signal.ema_20)
    bb_l = float(signal.bb_lower)
    bb_u = float(signal.bb_upper)
    rsi = float(signal.rsi)
    macd = float(signal.macd)
    volume = float(signal.volume)
    avg_volume = float(signal.avg_volume) or volume  # avoid div/0

    # EMA relationship as a percentage (positive = price above EMA).
    ema_pct = ((close - ema) / ema * 100.0) if ema else 0.0

    # Position within the Bollinger band, 0.0 = lower, 1.0 = upper.
    band_width = max(bb_u - bb_l, 1e-9)
    bb_pos = max(0.0, min(1.0, (close - bb_l) / band_width))

    # Volume vs 20-bar average — the LLM has no reference otherwise.
    volume_ratio = (volume / avg_volume) if avg_volume else 1.0
    if volume_ratio >= 1.5:
        volume_context = "well above 20-bar average"
    elif volume_ratio >= 1.1:
        volume_context = "above 20-bar average"
    elif volume_ratio >= 0.9:
        volume_context = "in line with 20-bar average"
    elif volume_ratio >= 0.6:
        volume_context = "below 20-bar average"
    else:
        volume_context = "well below 20-bar average"

    if rsi < 30:
        rsi_zone = "oversold"
    elif rsi < 45:
        rsi_zone = "weak"
    elif rsi <= 55:
        rsi_zone = "neutral"
    elif rsi <= 65:
        rsi_zone = "neutral-bullish"
    elif rsi <= 75:
        rsi_zone = "overbought-warning"
    else:
        rsi_zone = "overbought"

    if bb_pos < 0.25:
        bb_context = "near lower band"
    elif bb_pos < 0.55:
        bb_context = "lower-mid range"
    elif bb_pos < 0.8:
        bb_context = "upper-mid range"
    else:
        bb_context = "near upper band"

    return {
        "symbol": signal.symbol,
        "strategy": strategy_name,
        "close": round(close, 2),
        "rsi": round(rsi, 2),
        "rsi_zone": rsi_zone,
        "macd_diff": round(macd, 4),
        "macd_state": "positive" if macd > 0 else ("flat" if macd == 0 else "negative"),
        "ema_20": round(ema, 2),
        "ema_relation": (
            f"close {ema_pct:+.2f}% vs EMA20"
            f" ({'above' if close > ema else 'below'})"
        ),
        "bb_lower": round(bb_l, 2),
        "bb_upper": round(bb_u, 2),
        "bb_position_pct": round(bb_pos * 100, 1),
        "bb_context": bb_context,
        "volume": round(volume, 0),
        "avg_volume_20": round(avg_volume, 0),
        "volume_ratio": round(volume_ratio, 2),
        "volume_context": volume_context,
    }


def _build_prompt(features: dict[str, Any], news_summary: str) -> str:
    """Construct the analyst prompt.

    Frames the model as an Indian-equities swing analyst and asks for
    strict JSON with a fixed schema so parsing is robust. The prompt
    deliberately does not mention any internal filter / candidate flag
    so the model focuses on the technicals and news, not on validating
    upstream architecture.
    """
    feature_block = json.dumps(features, indent=2)
    news_block = news_summary.strip() or "No external news context provided."
    return (
        "You are an Indian-equities swing-trading analyst covering "
        "NSE-listed stocks. Analyze the technical posture and recent "
        "news context for the setup below. All prices are in INR. "
        "Provide concise, professional commentary — no hype, no "
        "certainty language, no financial-advice phrasing, no buy/sell "
        "recommendations. Use neutral observational tone. Do not invent "
        "price levels.\n\n"
        f"SETUP FEATURES:\n{feature_block}\n\n"
        f"NEWS CONTEXT:\n{news_block}\n\n"
        "Respond with STRICT JSON (no markdown, no prose outside JSON) using "
        "exactly these keys, each value a single short sentence:\n"
        "{\n"
        '  "thesis":        "one-sentence trade thesis grounded in the data",\n'
        '  "momentum":      "RSI + MACD interpretation",\n'
        '  "trend":         "EMA / price relationship interpretation",\n'
        '  "volume":        "volume behaviour vs the 20-bar average",\n'
        '  "setup_quality": "overall quality of the setup",\n'
        '  "risks":         "key risk observations or invalidation triggers"\n'
        "}"
    )


def _rule_based_commentary(features: dict[str, Any]) -> dict[str, str]:
    """Deterministic fallback commentary used when the LLM is unavailable."""
    return {
        "thesis": (
            f"{features['symbol']}: technical posture summarised mechanically "
            "under the swing framework; treat as observational, not a recommendation."
        ),
        "momentum": (
            f"RSI at {features['rsi']} ({features['rsi_zone']}); "
            f"MACD diff {features['macd_state']} ({features['macd_diff']})."
        ),
        "trend": (
            f"{features['ema_relation']} — short-term trend bias "
            f"{'up' if 'above' in features['ema_relation'] else 'down'}."
        ),
        "volume": (
            f"Latest volume {features['volume']:.0f} ({features['volume_ratio']}x "
            f"the 20-bar average — {features['volume_context']})."
        ),
        "setup_quality": (
            f"Price positioned {features['bb_context']} of the Bollinger range; "
            "absent qualitative confirmation, treat as watchlist-grade."
        ),
        "risks": (
            "Invalidation if close breaks below EMA20 or the lower Bollinger "
            "band; macro / sectoral news may override the technical setup."
        ),
    }


# --- Analyst -------------------------------------------------------------------
class GeminiTradeAnalyst:
    """LLM-backed analyst that produces a :class:`TradeAnalysis`.

    Falls back to rule-based commentary on missing API key, network
    error, or malformed model output — the scan loop must never crash
    because the LLM is unavailable.
    """

    def __init__(self, api_key: str, model: str = DEFAULT_GEMINI_MODEL):
        self.api_key = api_key
        self.model = model

    def analyze(
        self,
        signal: SetupSignal,
        strategy_name: str,
        news_summary: str = "",
        debug: bool = False,
        debug_sink: list[str] | None = None,
    ) -> TradeAnalysis:
        # debug_sink: optional list to which debug strings are appended
        # instead of being printed. Used by the parallel scan loop so
        # threads don't interleave stdout. When None, falls back to
        # print() for backward compatibility with direct callers.
        def _dbg(msg: str) -> None:
            if not debug:
                return
            if debug_sink is not None:
                debug_sink.append(msg)
            else:
                print(msg)

        features = _derive_features(signal, strategy_name)
        entry, target, stop, rr = compute_trade_levels(signal)

        if not self.api_key:
            _dbg("[debug] ai_brain: no GEMINI_API_KEY; using rule-based fallback.")
            return self._compose(signal, strategy_name, features, entry, target, stop, rr,
                                 _rule_based_commentary(features), news_summary, "fallback")

        prompt = _build_prompt(features, news_summary)
        _dbg(f"[debug] ai_brain prompt ({len(prompt)} chars):\n{prompt}")

        try:
            text = self._call_gemini(prompt)
        except Exception as exc:
            _dbg(f"[debug] ai_brain Gemini call failed: {exc}")
            return self._compose(signal, strategy_name, features, entry, target, stop, rr,
                                 _rule_based_commentary(features), news_summary, "fallback")

        _dbg(f"[debug] ai_brain response:\n{text}")

        commentary = _parse_commentary(text)
        if commentary is None:
            _dbg("[debug] ai_brain: response was not valid JSON; using fallback.")
            return self._compose(signal, strategy_name, features, entry, target, stop, rr,
                                 _rule_based_commentary(features), news_summary, "fallback")

        return self._compose(signal, strategy_name, features, entry, target, stop, rr,
                             commentary, news_summary, "llm")

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------
    def _call_gemini(self, prompt: str) -> str:
        endpoint = GEMINI_ENDPOINT.format(model=self.model, api_key=self.api_key)
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.3, "responseMimeType": "application/json"},
        }
        req = request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=20) as response:
            raw = json.loads(response.read().decode("utf-8"))
        return raw["candidates"][0]["content"]["parts"][0]["text"]

    @staticmethod
    def _compose(
        signal: SetupSignal,
        strategy_name: str,
        features: dict[str, Any],
        entry: float,
        target: float,
        stop: float,
        rr: float,
        commentary: dict[str, str],
        news_summary: str,
        source: str,
    ) -> TradeAnalysis:
        return TradeAnalysis(
            symbol=signal.symbol,
            strategy_name=strategy_name,
            direction="LONG",  # current strategies are long-only
            entry=entry,
            target=target,
            stop_loss=stop,
            risk_reward=rr,
            thesis=commentary["thesis"],
            momentum=commentary["momentum"],
            trend=commentary["trend"],
            volume=commentary["volume"],
            setup_quality=commentary["setup_quality"],
            risks=commentary["risks"],
            news_summary=news_summary,
            features=features,
            source=source,
        )


# Backward-compat alias. Older code paths called ``GeminiIdeaGenerator``
# and ``build_trade_idea(signal, news)``; both keep working.
class GeminiIdeaGenerator(GeminiTradeAnalyst):
    def build_trade_idea(self, signal: SetupSignal, news_summary: str) -> TradeAnalysis:
        return self.analyze(signal=signal, strategy_name="swing", news_summary=news_summary)


def _parse_commentary(text: str) -> dict[str, str] | None:
    """Best-effort JSON extraction from the model response."""
    text = (text or "").strip()
    # Strip an accidental ```json ... ``` fence if the model adds one.
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].lstrip()
    try:
        parsed = json.loads(text)
    except ValueError:
        return None
    required = ("thesis", "momentum", "trend", "volume", "setup_quality", "risks")
    if not all(k in parsed for k in required):
        return None
    return {k: str(parsed[k]).strip() for k in required}
