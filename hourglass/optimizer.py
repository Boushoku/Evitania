"""Cost/benefit ranking of sand-generator purchases (pure logic, no game access).

Model (generators only, upgrades are not modelled yet):
  - a generator's output is proportional to its level;
  - every milestone doubles that generator's output. Milestones are at levels
    25, 50, 100, 200, 300, ...;
  - costs are NOT modelled: they are read from the game (they change with discounts).
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Generator:
    name: str
    level: int
    rate: float  # current output, per second
    max_level: int | None = None


@dataclass(frozen=True)
class Option:
    gen: Generator
    add_levels: int
    cost: float


@dataclass(frozen=True)
class Result:
    option: Option
    new_rate: float
    gain_after: float
    total_seconds: float  # until the target, counting the wait to afford the purchase
    saved_seconds: float  # vs. buying nothing (negative = makes it worse)


def milestones_passed(level: int) -> int:
    return (level >= 25) + (level >= 50) + level // 100


def levels_to_next_milestone(level: int) -> int:
    for m in (25, 50):
        if level < m:
            return m - level
    return 100 - level % 100


def rate_after(gen: Generator, add_levels: int) -> float:
    if gen.level <= 0 or gen.rate <= 0 or add_levels < 0:
        raise ValueError("generator needs level > 0 and rate > 0")
    new_level = gen.level + add_levels
    if gen.max_level is not None:
        new_level = min(new_level, gen.max_level)
    doublings = milestones_passed(new_level) - milestones_passed(gen.level)
    return gen.rate * new_level / gen.level * 2 ** doublings


def evaluate(opt: Option, gain: float, sand: float, progress: float, target: float) -> Result:
    """`progress` is the lifetime counter shown next to the target (spending does not reduce it)."""
    if gain <= 0:
        raise ValueError("gain must be positive")
    new_rate = rate_after(opt.gen, opt.add_levels)
    gain_after = gain - opt.gen.rate + new_rate
    wait = max(opt.cost - sand, 0.0) / gain
    remaining = max(target - progress - gain * wait, 0.0)
    total = wait + remaining / gain_after
    base = max(target - progress, 0.0) / gain
    return Result(opt, new_rate, gain_after, total, base - total)


def rank(options: list[Option], gain: float, sand: float, progress: float, target: float) -> list[Result]:
    """Best first (shortest time to the target)."""
    return sorted((evaluate(o, gain, sand, progress, target) for o in options),
                  key=lambda r: r.total_seconds)
