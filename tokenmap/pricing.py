"""Model pricing and cost calculation for tokenmap."""

from __future__ import annotations

from dataclasses import dataclass, field
from tokenmap.types import ModelTokenDetail


@dataclass
class ModelPricing:
    """Pricing per million tokens (USD)."""

    input_per_m: float = 0.0
    output_per_m: float = 0.0
    cache_read_per_m: float = 0.0
    cache_write_per_m: float = 0.0


@dataclass
class ModelCost:
    """Computed cost for a single model."""

    model: str = ""
    input_cost: float = 0.0
    output_cost: float = 0.0
    cache_read_cost: float = 0.0
    cache_write_cost: float = 0.0
    total_cost: float = 0.0
    tokens: ModelTokenDetail = field(default_factory=ModelTokenDetail)


@dataclass
class CostSummary:
    """Aggregated cost summary across all models."""

    total_cost: float = 0.0
    model_costs: list[ModelCost] = field(default_factory=list)


# Pricing per 1M tokens (USD)
# Source: https://platform.claude.com/docs/en/about-claude/pricing
#         https://openai.com/api/pricing/
PRICING: dict[str, ModelPricing] = {
    # === Claude Models (official pricing from platform.claude.com) ===

    # Opus 4.7 — $5 input, $25 output
    "claude-opus-4-7": ModelPricing(5, 25, 0.50, 6.25),

    # Opus 4.6 — $5 input, $25 output
    "claude-opus-4-6": ModelPricing(5, 25, 0.50, 6.25),

    # Opus 4.5 — $5 input, $25 output
    "claude-opus-4-5": ModelPricing(5, 25, 0.50, 6.25),

    # Opus 4.1 — $15 input, $75 output
    "claude-opus-4-1": ModelPricing(15, 75, 1.50, 18.75),

    # Opus 4 — $15 input, $75 output
    "claude-opus-4-20250514": ModelPricing(15, 75, 1.50, 18.75),
    "claude-opus-4": ModelPricing(15, 75, 1.50, 18.75),

    # Sonnet 4.6 — $3 input, $15 output
    "claude-sonnet-4-6": ModelPricing(3, 15, 0.30, 3.75),

    # Sonnet 4.5 — $3 input, $15 output
    "claude-sonnet-4-5": ModelPricing(3, 15, 0.30, 3.75),

    # Sonnet 4 — $3 input, $15 output
    "claude-sonnet-4-20250514": ModelPricing(3, 15, 0.30, 3.75),
    "claude-sonnet-4": ModelPricing(3, 15, 0.30, 3.75),

    # Sonnet 3.7 (deprecated) — $3 input, $15 output
    "claude-3-7-sonnet": ModelPricing(3, 15, 0.30, 3.75),

    # Haiku 4.5 — $1 input, $5 output
    "claude-haiku-4-5": ModelPricing(1, 5, 0.10, 1.25),

    # Haiku 3.5 — $0.80 input, $4 output
    "claude-haiku-4-5-20251001": ModelPricing(0.80, 4, 0.08, 1.0),
    "claude-3-5-haiku-20241022": ModelPricing(0.80, 4, 0.08, 1.0),
    "claude-3-5-haiku": ModelPricing(0.80, 4, 0.08, 1.0),

    # Sonnet 3.5 (deprecated) — $3 input, $15 output
    "claude-3-5-sonnet-20241022": ModelPricing(3, 15, 0.30, 3.75),
    "claude-3-5-sonnet-20240620": ModelPricing(3, 15, 0.30, 3.75),

    # Opus 3 (deprecated) — $15 input, $75 output
    "claude-3-opus-20240229": ModelPricing(15, 75, 1.50, 18.75),

    # Haiku 3 — $0.25 input, $1.25 output
    "claude-3-haiku-20240307": ModelPricing(0.25, 1.25, 0.03, 0.30),

    # === OpenAI Models ===
    "gpt-4o": ModelPricing(2.5, 10, 1.25, 2.5),
    "gpt-4o-2024-08-06": ModelPricing(2.5, 10, 1.25, 2.5),
    "gpt-4o-mini": ModelPricing(0.15, 0.60, 0.075, 0.15),
    "gpt-4-turbo": ModelPricing(10, 30, 5, 10),
    "o1": ModelPricing(15, 60, 7.5, 15),
    "o1-mini": ModelPricing(3, 12, 1.5, 3),
    "o3": ModelPricing(10, 40, 2.5, 10),
    "o3-mini": ModelPricing(1.10, 4.40, 0.55, 1.10),
    "o4-mini": ModelPricing(1.10, 4.40, 0.55, 1.10),
    "codex-mini-latest": ModelPricing(1.50, 6, 0.75, 1.50),
}

# Conservative default for unknown models
DEFAULT_PRICING = ModelPricing(
    input_per_m=3,
    output_per_m=15,
    cache_read_per_m=0.30,
    cache_write_per_m=3.75,
)


def get_pricing(model: str) -> ModelPricing:
    """Look up pricing for a model, using prefix/substring matching for versioned names."""
    # Exact match
    if model in PRICING:
        return PRICING[model]

    # Prefix match (e.g. "claude-opus-4-6-20260101" → "claude-opus-4-6")
    for key in PRICING:
        if model.startswith(key):
            return PRICING[key]

    # Substring match (e.g. "anthropic/claude-3-5-sonnet" → match "claude-3-5-sonnet-*")
    for key in PRICING:
        if key in model or model in key:
            return PRICING[key]

    return DEFAULT_PRICING


def _calculate_model_cost(model: str, tokens: ModelTokenDetail) -> ModelCost:
    """Calculate cost for specific token counts and a model."""
    pricing = get_pricing(model)

    input_cost = (tokens.input_tokens / 1_000_000) * pricing.input_per_m
    output_cost = (tokens.output_tokens / 1_000_000) * pricing.output_per_m
    cache_read_cost = (tokens.cache_read_tokens / 1_000_000) * pricing.cache_read_per_m
    cache_write_cost = (tokens.cache_write_tokens / 1_000_000) * pricing.cache_write_per_m

    return ModelCost(
        model=model,
        input_cost=input_cost,
        output_cost=output_cost,
        cache_read_cost=cache_read_cost,
        cache_write_cost=cache_write_cost,
        total_cost=input_cost + output_cost + cache_read_cost + cache_write_cost,
        tokens=tokens,
    )


def compute_cost_summary(
    detailed_model_usage: dict[str, ModelTokenDetail],
) -> CostSummary:
    """Compute cost summary from a detailed model usage map."""
    model_costs: list[ModelCost] = []

    for model, tokens in detailed_model_usage.items():
        cost = _calculate_model_cost(model, tokens)
        if cost.total_cost > 0:
            model_costs.append(cost)

    # Sort by cost descending
    model_costs.sort(key=lambda mc: mc.total_cost, reverse=True)

    total_cost = sum(mc.total_cost for mc in model_costs)

    return CostSummary(total_cost=total_cost, model_costs=model_costs)


def format_cost(cost: float) -> str:
    """Format a USD cost value for display."""
    if cost >= 1000:
        return f"${cost / 1000:.1f}K"
    if cost >= 100:
        return f"${cost:.0f}"
    if cost >= 10:
        return f"${cost:.1f}"
    if cost >= 1:
        return f"${cost:.2f}"
    if cost >= 0.01:
        return f"${cost:.2f}"
    if cost >= 0.001:
        return f"${cost:.3f}"
    if cost == 0:
        return "$0.00"
    return f"${cost:.4f}"
