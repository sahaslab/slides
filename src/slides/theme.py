import collections
from dataclasses import dataclass, field
from slides import color
from slides.model import ColorUse, Deck

NEUTRAL_CHROMA = 0.04
ACCENT_CHROMA = 0.05
ACCENT_CONTRAST = 3.0
TEXT_CONTRAST = 4.5
DUPLICATE = 0.06
CHAIN_LIMIT = 2.0 * DUPLICATE
GOLDEN_ANGLE = 137.5
MAX_TURNS = 720
PAD_CONTRAST_LADDER = (ACCENT_CONTRAST, 4.5, 6.5, 9.0, 13.0)


@dataclass
class DeckTheme:
    background: str
    foreground: str
    muted: str
    grid: str
    accents: list[str] = field(default_factory=list)
    fonts: dict[str, str] = field(default_factory=dict)
    source: str = ""

    def to_dict(self) -> dict:
        return {
            "background": self.background,
            "foreground": self.foreground,
            "muted": self.muted,
            "grid": self.grid,
            "accents": list(self.accents),
            "fonts": dict(self.fonts),
            "source": self.source,
        }


def extract(
    deck: Deck,
    accents: int = 6,
) -> DeckTheme:
    candidates = [ColorUse(c.hex.lower(), c.weight, c.kind) for c in deck.colors]
    background = _background(deck, candidates)
    foreground = _foreground(candidates, background)
    muted = _muted(candidates, background, foreground)
    grid = _grid(candidates, background, foreground)
    if color.contrast(grid, background) >= color.contrast(muted, background):
        # A real grid candidate always beats a real muted one (the bands are
        # disjoint either side of 2:1), but a fallback mix does not carry
        # that guarantee: nudge grid further toward the background instead
        # of letting it end up louder than muted.
        grid = color.mix(muted, background, 0.5)
    return DeckTheme(
        background=background,
        foreground=foreground,
        muted=muted,
        grid=grid,
        accents=_accents(candidates, background, foreground, accents),
        fonts=dict(deck.fonts),
        source=deck.source,
    )


def _background(
    deck: Deck,
    candidates: list[ColorUse],
) -> str:
    explicit = [s.background.lower() for s in deck.slides if s.background]
    if explicit:
        return collections.Counter(explicit).most_common(1)[0][0]
    tiers = [
        [c for c in candidates if c.kind == "background"],
        [c for c in candidates if c.kind != "text" and _neutral(c.hex)],
        [c for c in candidates if c.kind != "text"],
    ]
    for pool in tiers:
        if pool:
            return max(pool, key=lambda c: (c.weight, c.hex)).hex
    return "#ffffff"


def _foreground(
    candidates: list[ColorUse],
    background: str,
) -> str:
    text = [c for c in candidates if c.kind == "text"] or candidates
    if not text:
        extreme = "#ffffff" if color.contrast_extreme(background) == 1.0 else "#000000"
        return color.with_contrast(extreme, background, TEXT_CONTRAST)
    neutral = [c for c in text if _neutral(c.hex)]
    clearing = [c for c in neutral if color.contrast(c.hex, background) >= TEXT_CONTRAST]
    if clearing:
        return max(clearing, key=lambda c: (c.weight, c.hex)).hex
    best = max(text, key=lambda c: (c.weight, c.hex))
    return color.with_contrast(best.hex, background, TEXT_CONTRAST)


def _muted(
    candidates: list[ColorUse],
    background: str,
    foreground: str,
) -> str:
    ceiling = color.contrast(foreground, background)
    band = [
        c for c in candidates
        if c.kind == "text"
        and _neutral(c.hex)
        and 2.0 <= color.contrast(c.hex, background) < ceiling
    ]
    if not band:
        return color.mix(foreground, background, 0.55)
    return max(band, key=lambda c: (c.weight, c.hex)).hex


def _grid(
    candidates: list[ColorUse],
    background: str,
    foreground: str,
) -> str:
    band = [
        c for c in candidates
        if _neutral(c.hex) and 1.1 <= color.contrast(c.hex, background) < 2.0
    ]
    if not band:
        return color.mix(foreground, background, 0.85)
    return max(band, key=lambda c: (c.weight, c.hex)).hex


def _accents(
    candidates: list[ColorUse],
    background: str,
    foreground: str,
    count: int,
) -> list[str]:
    chromatic = [c for c in candidates if color.to_oklch(c.hex)[1] >= ACCENT_CHROMA]
    chromatic.sort(key=lambda c: (-c.weight, c.hex))
    clusters: list[list[str]] = []
    for candidate in chromatic:
        raised = color.with_contrast(candidate.hex, background, ACCENT_CONTRAST)
        _absorb(clusters, raised)
    kept = [cluster[0] for cluster in clusters]
    # Prefer accents that read as distinct from the running foreground, but
    # never at the cost of discarding the deck's only real accent signal
    # (a monochrome deck can legitimately use one colour as both).
    distinct = [c for c in kept if color.delta_e(c, foreground) >= DUPLICATE]
    kept = distinct or kept
    spread = _spread(kept, count)
    return _pad(spread, background, foreground, count)


def _absorb(
    clusters: list[list[str]],
    raised: str,
) -> None:
    # Single-link clustering, hardened against chaining: a candidate joins a
    # cluster if it is near ANY member of it (so a gradient family collapses
    # to one entry) AND still within CHAIN_LIMIT of the cluster's own leader
    # (its first, heaviest member), so a chain of near-duplicates cannot walk
    # its way to a colour that no longer resembles where the cluster began.
    # The brief's own dedup rule never grouped members at all: a rejected
    # candidate was simply discarded, so its all(...) check was really
    # comparing each candidate only against the leaders already kept, not
    # against every member of a resemblance chain.
    for cluster in clusters:
        near_member = any(color.delta_e(raised, member) < DUPLICATE for member in cluster)
        near_leader = color.delta_e(raised, cluster[0]) < CHAIN_LIMIT
        if near_member and near_leader:
            cluster.append(raised)
            return
    clusters.append([raised])


def _spread(
    accents: list[str],
    count: int,
) -> list[str]:
    if len(accents) <= count:
        return accents
    chosen = [accents[0]]
    remaining = accents[1:]
    while len(chosen) < count and remaining:
        pick = max(
            remaining,
            key=lambda c: (
                min(_hue_gap(color.to_oklch(c)[2], color.to_oklch(p)[2]) for p in chosen),
                c,
            ),
        )
        chosen.append(pick)
        remaining.remove(pick)
    return chosen


def _pad(
    accents: list[str],
    background: str,
    foreground: str,
    count: int,
) -> list[str]:
    # Derive the shortfall by rotating the deck's own hues, never from a
    # palette shipped with the tool. Rotating by a fixed 360/count step can
    # exhaust a single base after only count-1 distinct hues and then repeat
    # exactly, losing a slot for good; the golden angle never lands back on
    # a prior turn, so there is always a fresh candidate to try. Every
    # colour kept so far (real or already padded) is also a rotation base,
    # so the pool of candidates per turn grows as padding succeeds instead
    # of being pinned to the handful of hues the deck actually used. A
    # single fixed lightness (the minimum that clears ACCENT_CONTRAST) only
    # has so much gamut-boundary arc to go around before it cannot fit one
    # more mutually distinguishable colour; cycling the target ratio up the
    # ladder pushes some candidates to a different lightness shell, which
    # is a differently-shaped, usually roomier arc, without ever dropping
    # below the contrast floor. At each turn every (base, ratio) pair is a
    # candidate, and whichever maximises the minimum hue gap to everything
    # already kept (and stays clear of the foreground) is taken.
    if not accents:
        seed = color.with_contrast(
            color.from_oklch(0.75, 0.15, 150.0),
            background,
            ACCENT_CONTRAST,
        )
        accents = [seed]
    out = list(accents)
    turn = 1
    while len(out) < count and turn <= MAX_TURNS:
        bases = [color.to_oklch(hex_) for hex_ in out]
        rotated = [
            color.with_contrast(
                color.from_oklch(L, C, (H + GOLDEN_ANGLE * turn) % 360.0),
                background,
                ratio,
            )
            for L, C, H in bases
            for ratio in PAD_CONTRAST_LADDER
        ]
        fresh = [
            c for c in rotated
            if all(color.delta_e(c, other) >= DUPLICATE for other in out)
            and color.delta_e(c, foreground) >= DUPLICATE
        ]
        if fresh:
            picked = max(
                fresh,
                key=lambda c: (
                    min(_hue_gap(color.to_oklch(c)[2], color.to_oklch(o)[2]) for o in out),
                    c,
                ),
            )
            out.append(picked)
        turn += 1
    return out[:count]


def _neutral(hex_: str) -> bool:
    return color.to_oklch(hex_)[1] < NEUTRAL_CHROMA


def _hue_gap(
    one: float,
    other: float,
) -> float:
    gap = abs(one - other) % 360.0
    return min(gap, 360.0 - gap)
