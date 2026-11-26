from __future__ import annotations

import argparse
import json
import os
import sys
import tomllib
from pathlib import Path
from typing import Any

try:
    from scripts.legacy_routing import migrate_legacy_routing
except ModuleNotFoundError:
    from legacy_routing import migrate_legacy_routing

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
KIMI_HOME = Path(os.environ.get("KIMI_CODE_HOME") or (Path.home() / ".kimi-code"))
TIER_WEIGHTS = {
    "L1": {"quality": 0.25, "cost": 0.40, "speed": 0.20, "confidence": 0.15},
    "L2": {"quality": 0.55, "cost": 0.20, "speed": 0.10, "confidence": 0.15},
}
STRATEGIES = {
    "balanced": {"quality": 1.0, "cost": 1.0, "speed": 1.0, "confidence": 1.0},
    "cost": {"quality": 0.55, "cost": 1.55, "speed": 1.35, "confidence": 0.8},
    "quality": {"quality": 1.25, "cost": 0.35, "speed": 0.55, "confidence": 1.15},
}


def read_json(path: Path, fallback: Any) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return fallback


def number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value < 0 or value > 100:
        return None
    return float(value)


def confidence(value: Any) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if 0 <= value <= 1:
            return float(value)
        if 1 < value <= 100:
            return value / 100
    if isinstance(value, str):
        return {"high": 0.9, "medium": 0.65, "low": 0.35}.get(value.lower(), 0.35)
    return 0.35


def average(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


class AutoRouter:
    def __init__(self) -> None:
        with (KIMI_HOME / "config.toml").open("rb") as handle:
            self.config = tomllib.load(handle)
        self.pool = set(self.config.get("secondary_model", {}).get("models", {}).keys())
        self.models = self.config.get("models", {})
        self.insights = read_json(KIMI_HOME / "model-insights.json", {}).get("models", {})
        override = KIMI_HOME / "multimodel-orchestrator.routing.json"
        self.routing = migrate_legacy_routing(read_json(override if override.exists() else PLUGIN_ROOT / "routing.json", {}))

    def supports(self, alias: str, capability: str) -> bool:
        verified = self.insights.get(alias, {}).get("verified", {})
        if verified.get(capability) is False:
            return False
        configured = set(self.models.get(alias, {}).get("capabilities", []))
        return capability in configured or verified.get(capability) is True

    def quality(self, alias: str, modality: str) -> float | None:
        scores = self.insights.get(alias, {}).get("scores", {})
        if modality in {"image", "video"}:
            vision = number(scores.get("vision"))
            if vision is not None:
                return vision
        coding = number(scores.get("coding"))
        reasoning = number(scores.get("reasoning"))
        if coding is not None and reasoning is not None:
            return (coding + reasoning) / 2
        return coding if coding is not None else reasoning

    def neutral(self, value: Any) -> float:
        return number(value) if number(value) is not None else 50.0

    def candidate(self, alias: str, tier: str, modality: str, strategy: str) -> dict[str, Any] | None:
        quality = self.quality(alias, modality)
        if quality is None:
            return None
        insight = self.insights.get(alias, {})
        scores = insight.get("scores", {})
        cost = self.neutral(scores.get("cost_efficiency"))
        speed = self.neutral(scores.get("speed"))
        certainty = confidence(insight.get("confidence")) * 100
        weights = {
            key: TIER_WEIGHTS[tier][key] * STRATEGIES[strategy][key]
            for key in TIER_WEIGHTS[tier]
        }
        total_weight = sum(weights.values())
        fit = (
            weights["quality"] * quality
            + weights["cost"] * cost
            + weights["speed"] * speed
            + weights["confidence"] * certainty
        ) / total_weight
        return {
            "alias": alias,
            "model": self.models[alias].get("model", alias),
            "score": round(fit, 1),
            "quality_score": round(quality, 1),
            "cost_score": round(cost, 1),
            "speed_score": round(speed, 1),
            "confidence": round(certainty / 100, 2),
            "weights": {key: round(value / total_weight, 3) for key, value in weights.items()},
            "evidence": insight.get("evidence", [])[:3],
            "verified": insight.get("verified", {}),
            "reason": "按任务等级、模态、成本/速度和资料置信度计算的本地启发式适配分，不是统一 benchmark",
        }

    def route(self, tier: str, modality: str, strategy: str) -> dict[str, Any]:
        eligible = [
            alias for alias in self.pool
            if alias in self.models
            and self.supports(alias, "tool_use")
            and self.supports(alias, {"text": "tool_use", "image": "image_in", "video": "video_in"}[modality])
        ]
        candidates = []
        for alias in eligible:
            candidate = self.candidate(alias, tier, modality, strategy)
            if candidate is not None:
                candidates.append(candidate)
        candidates.sort(key=lambda item: (-item["score"], -item["confidence"], item["alias"]))
        if candidates:
            return {"mode": "auto", "fallback": False, "tier": tier, "modality": modality, "strategy": strategy, "candidates": candidates}
        fallback_routes = self.routing.get("autoRoutes", self.routing.get("routes", {}))
        fallback_alias = fallback_routes.get(tier, {}).get(modality)
        if fallback_alias not in eligible:
            fallback_alias = eligible[0] if eligible else None
        if fallback_alias is None:
            raise ValueError(f"模型池中没有满足 {tier}/{modality} 和 tool_use 的模型")
        return {
            "mode": "auto",
            "fallback": True,
            "tier": tier,
            "modality": modality,
            "strategy": strategy,
            "candidates": [{
                "alias": fallback_alias,
                "model": self.models[fallback_alias].get("model", fallback_alias),
                "score": None,
                "reason": "缺少足够的可靠评分资料，使用当前路由回退；没有虚构评分",
                "evidence": [],
            }],
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tier", required=True, choices=["L1", "L2"])
    parser.add_argument("--modality", required=True, choices=["text", "image", "video"])
    parser.add_argument("--strategy", default="balanced", choices=["balanced", "cost", "quality"])
    args = parser.parse_args()
    try:
        result = AutoRouter().route(args.tier, args.modality, args.strategy)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, tomllib.TOMLDecodeError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
