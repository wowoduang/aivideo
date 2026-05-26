from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Dict, Iterable, List


@dataclass(frozen=True)
class PriceRule:
    event_type: str
    provider: str
    unit_name: str
    unit_cost: float

    def matches(self, *, event_type: str, provider: str, unit_name: str) -> bool:
        return all([
            self.event_type in {"*", event_type},
            self.provider in {"*", provider},
            self.unit_name in {"*", unit_name},
        ])


def _parse_rule_key(key: str) -> tuple[str, str, str]:
    parts = str(key or "").split(":")
    if len(parts) != 3:
        raise ValueError(f"usage price key must be event_type:provider:unit_name, got {key!r}")
    return parts[0].strip() or "*", parts[1].strip() or "*", parts[2].strip() or "*"


@lru_cache(maxsize=1)
def load_price_rules() -> List[PriceRule]:
    """Load deployment-specific usage price rules from env JSON.

    AIVIDEO_USAGE_PRICES_JSON format:
      {"llm_prompt_tokens:openai:tokens": 0.00000015,
       "tts_characters:azure:characters": 0.000016}
    """

    raw = os.getenv("AIVIDEO_USAGE_PRICES_JSON", "").strip()
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, dict):
        return []
    rules: List[PriceRule] = []
    for key, value in payload.items():
        try:
            event_type, provider, unit_name = _parse_rule_key(str(key))
            rules.append(PriceRule(event_type=event_type, provider=provider, unit_name=unit_name, unit_cost=float(value)))
        except Exception:
            continue
    # Prefer most-specific rules before wildcard rules.
    rules.sort(key=lambda r: (r.event_type == "*", r.provider == "*", r.unit_name == "*"))
    return rules


def estimate_cost(*, event_type: str, provider: str, unit_name: str, units: int) -> float:
    event_type = str(event_type or "")
    provider = str(provider or "")
    unit_name = str(unit_name or "")
    units_i = max(0, int(units or 0))
    for rule in load_price_rules():
        if rule.matches(event_type=event_type, provider=provider, unit_name=unit_name):
            return float(units_i) * float(rule.unit_cost)
    return 0.0


def pricing_status() -> Dict[str, Any]:
    rules = load_price_rules()
    return {
        "configured": bool(rules),
        "rule_count": len(rules),
        "rules": [
            {
                "event_type": rule.event_type,
                "provider": rule.provider,
                "unit_name": rule.unit_name,
                "unit_cost": rule.unit_cost,
            }
            for rule in rules
        ],
    }


def clear_cache() -> None:
    load_price_rules.cache_clear()
