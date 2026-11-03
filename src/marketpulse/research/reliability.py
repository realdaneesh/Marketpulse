"""Episode-level descriptive association and conservative dependence-aware safeguards."""

import random

from marketpulse.research.models import ResearchConfig, SequenceResult


def adjust(p_values: list[float | None], dependent: bool = True) -> list[float | None]:
    """BH, or BY for arbitrary dependence. Unavailable hypotheses retain family size."""
    if any(p is not None and not 0 <= p <= 1 for p in p_values):
        raise ValueError("p-values must be in [0,1]")
    count = len(p_values)
    factor = sum(1 / i for i in range(1, count + 1)) if dependent else 1
    order = sorted(range(count), key=lambda i: 1 if p_values[i] is None else p_values[i])
    result = [None] * count
    previous = 1.0
    for rank in range(count, 0, -1):
        index = order[rank - 1]
        p = p_values[index]
        previous = min(previous, (1 if p is None else p) * count * factor / rank, 1)
        if p is not None:
            result[index] = previous
    return result


def counts(a: list[bool], b: list[bool], lag: int) -> tuple[int, ...]:
    """Each episode starts after observed false; windows do not overlap or share followers.

    Block-boundary active episodes are left-censored. Onset time is the finalized
    end of the first flagged candle; simultaneous onsets are counted separately.
    Controls have no active leader anywhere in their exposure window.
    """
    leader = {i for i in range(1, len(a)) if a[i] and not a[i - 1]}
    follower = {i for i in range(1, len(b)) if b[i] and not b[i - 1]}
    opportunities = hits = controls = control_hits = 0
    next_index = 1
    for i in range(1, len(a) - lag):
        if i < next_index:
            continue
        if i in leader:
            opportunities += 1
            hits += any(j in follower for j in range(i + 1, i + lag + 1))
        elif not any(a[i : i + lag + 1]):
            controls += 1
            control_hits += any(j in follower for j in range(i + 1, i + lag + 1))
        else:
            continue
        next_index = i + lag + 1
    return (
        opportunities,
        hits,
        controls,
        control_hits,
        len(leader),
        len(follower),
        len(leader & follower),
    )


def effect(values: tuple[int, ...]) -> float | None:
    n, h, c, ch = values[:4]
    return h / n - ch / c if n and c else None


def pooled(blocks: list[tuple[int, ...]]) -> tuple[int, ...]:
    return tuple(sum(x[i] for x in blocks) for i in range(7))


def sequence(
    leader: str,
    follower: str,
    fold: str,
    runs: list[tuple[list[bool], list[bool]]],
    expected: int,
    config: ResearchConfig,
    minimum_block: int,
) -> SequenceResult:
    """Fixed disjoint blocks; never sample through a source gap or fold boundary.

    P-values are block-permutation surrogates, not distribution-free significance.
    Stationarity/exchangeability between blocks remains an assumption.
    """
    size = max(config.block_length, minimum_block, 2 * config.max_lag + 3)
    blocks = [
        (a[i : i + size], b[i : i + size])
        for a, b in runs
        for i in range(0, len(a) - size + 1, size)
    ]
    summaries = [counts(a, b, config.max_lag) for a, b in blocks]
    total = pooled(summaries)
    n, h, c, ch, na, nb, simultaneous = total
    eligible = sum(len(a) for a, _ in runs)
    coverage = len(blocks) * size / expected if expected else 0.0
    delta = effect(total)
    supported = (
        len(blocks) >= config.minimum_blocks
        and na >= config.minimum_episodes
        and nb >= config.minimum_episodes
        and n >= config.minimum_episodes
        and c >= config.minimum_controls
        and coverage >= 0.8
        and delta is not None
    )
    interval = p_value = None
    if supported:
        rng = random.Random(config.seed)
        boot = []
        null = []
        for _ in range(config.resamples):
            value = effect(pooled([rng.choice(summaries) for _ in summaries]))
            if value is not None:
                boot.append(value)
            followers = [b for _, b in blocks]
            rng.shuffle(followers)
            shifted = [
                counts(a, b, config.max_lag) for (a, _), b in zip(blocks, followers, strict=True)
            ]
            value = effect(pooled(shifted))
            if value is not None:
                null.append(value)
        if min(len(boot), len(null)) >= 0.9 * config.resamples:
            boot.sort()
            interval = (boot[int(0.025 * (len(boot) - 1))], boot[int(0.975 * (len(boot) - 1))])
            p_value = (1 + sum(v >= delta for v in null)) / (1 + len(null))
    return SequenceResult(
        leader=leader,
        follower=follower,
        segment=fold,
        status="exploratory" if p_value is not None else "insufficient_data",
        lag_intervals=config.max_lag,
        eligible_intervals=eligible,
        expected_intervals=expected,
        coverage=coverage,
        blocks=len(blocks),
        leader_episodes=na,
        follower_episodes=nb,
        opportunities=n,
        following_events=h,
        control_opportunities=c,
        control_events=ch,
        simultaneous=simultaneous,
        conditional_rate=h / n if n else None,
        baseline_rate=ch / c if c else None,
        lift=(h / n) / (ch / c) if n and c and ch else None,
        effect=delta,
        interval=interval,
        p_value=p_value,
        explanation=(
            f"{leader} episode onset at t precedes {follower} onset in (t,t+"
            f"{config.max_lag} intervals]. Non-overlapping opportunities; simultaneous excluded. "
            "Controls have no active leader during exposure. Inference requires >=80% block "
            "coverage, sufficient episodes/controls and disjoint blocks. Short block tails "
            "are excluded. Blocks may retain residual dependence. Percentile block bootstrap "
            "and follower-block permutations assume stationarity and exchangeability across "
            "blocks; block boundaries are censored. One-sided positive association; "
            "not causality, forecast performance, or calibrated confidence."
        ),
    )
