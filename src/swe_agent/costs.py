"""Token and dollar accounting.

Prices are USD per 1M tokens. Local and free-tier models are $0. Fill in real
prices for paid models from the provider's pricing page before running.
"""

from dataclasses import dataclass, field

PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    # model name: (input, output)
}


def price(model: str, input_tokens: int, output_tokens: int) -> float:
    inp, out = PRICES_PER_MTOK.get(model, (0.0, 0.0))
    return (input_tokens * inp + output_tokens * out) / 1_000_000


@dataclass
class CostTracker:
    input_tokens: int = 0
    output_tokens: int = 0
    dollars: float = 0.0
    calls: int = 0
    cache_hits: int = 0
    by_model: dict[str, float] = field(default_factory=dict)

    def record(self, model: str, input_tokens: int, output_tokens: int, cached: bool) -> None:
        self.calls += 1
        if cached:
            self.cache_hits += 1
            return
        cost = price(model, input_tokens, output_tokens)
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.dollars += cost
        self.by_model[model] = self.by_model.get(model, 0.0) + cost

    def summary(self) -> dict:
        return {
            "calls": self.calls,
            "cache_hits": self.cache_hits,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "dollars": round(self.dollars, 6),
            "by_model": {k: round(v, 6) for k, v in self.by_model.items()},
        }
