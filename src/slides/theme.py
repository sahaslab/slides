import collections
from dataclasses import dataclass, field
from slides import color
from slides.model import ColorUse, Deck

NEUTRAL_CHROMA = 0.04
ACCENT_CHROMA = 0.05
ACCENT_CONTRAST = 3.0
TEXT_CONTRAST = 4.5
FOREGROUND_SYNTH_CONTRAST = 7.0
DUPLICATE = 0.06
CHAIN_LIMIT = 2.0 * DUPLICATE
GOLDEN_ANGLE = 137.5
MAX_TURNS = 720
PAD_RUNGS_PER_SIDE = 6


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
        return color.with_contrast("#ffffff", background, TEXT_CONTRAST)
    neutral = [c for c in text if _neutral(c.hex)]
    clearing = [c for c in neutral if color.contrast(c.hex, background) >= TEXT_CONTRAST]
    if clearing:
        return max(clearing, key=lambda c: (c.weight, c.hex)).hex
    best = max(text, key=lambda c: (c.weight, c.hex))
    if color.contrast(best.hex, background) >= TEXT_CONTRAST:
        return best.hex
    return color.with_contrast(best.hex, background, FOREGROUND_SYNTH_CONTRAST)


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
        and color.delta_e(c.hex, foreground) >= CHAIN_LIMIT
    ]
    if not band:
        return color.mix(foreground, background, 0.55)
    return max(band, key=lambda c: (c.weight, color.contrast(c.hex, background), c.hex)).hex


def _grid(
    candidates: list[ColorUse],
    background: str,
    foreground: str,
) -> str:
    fg_side = color.luminance(foreground) > color.luminance(background)
    band = [
        c for c in candidates
        if _neutral(c.hex)
        and 1.1 <= color.contrast(c.hex, background) < 2.0
        and (color.luminance(c.hex) > color.luminance(background)) == fg_side
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
    # Single-link clustering: a candidate joins a cluster if it is near ANY
    # member of it, so a gradient family collapses to one entry instead of
    # splitting wherever two adjacent steps happen to exceed DUPLICATE. Also
    # bounded by CHAIN_LIMIT to the cluster's leader (its first, heaviest
    # member), so a long chain can't drift arbitrarily far from where it
    # started.
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


def _pad_options(background: str) -> list[tuple[float, float]]:
    # (ratio, target) pairs to try, scaled to what this background can
    # actually reach in each direction: PAD_RUNGS_PER_SIDE lightness shells
    # spanning ACCENT_CONTRAST up to that side's own ceiling (contrast
    # against the pure extreme). A background where one side is capped
    # close to ACCENT_CONTRAST (mid-greys such as #707070-#888888) still
    # gets several usable shells instead of one; a mid-toned background
    # where both sides clear the floor gets shells on both sides of it,
    # doubling the room. A side below the floor contributes nothing, since
    # every rung on it would just clamp to the same unreachable extreme.
    options = []
    for target in (1.0, 0.0):
        ceiling = color.contrast("#ffffff" if target == 1.0 else "#000000", background)
        if ceiling < ACCENT_CONTRAST:
            continue
        span = ceiling - ACCENT_CONTRAST
        steps = PAD_RUNGS_PER_SIDE - 1
        options.extend(
            (ACCENT_CONTRAST + span * i / steps, target) for i in range(PAD_RUNGS_PER_SIDE)
        )
    return options


def _pad(
    accents: list[str],
    background: str,
    foreground: str,
    count: int,
) -> list[str]:
    # Derives the shortfall by rotating the deck's own hues by the golden
    # angle, never from a palette shipped with the tool. Every colour kept
    # so far, not just the deck's original hues, is also a rotation base,
    # so the candidate pool grows as padding succeeds. Rungs are walked in
    # order and the first one that yields a fresh candidate is taken: a
    # single lightness only fits so many mutually distinguishable hues, so
    # trying every rung and picking the best across all of them just adds
    # near-duplicates that round to the same hex once several bases share
    # a lightness.
    if not accents:
        seed = color.with_contrast(
            color.from_oklch(0.75, 0.15, 150.0),
            background,
            ACCENT_CONTRAST,
        )
        accents = [seed]
    out = list(accents)
    options = _pad_options(background)
    turn = 1
    while len(out) < count and turn <= MAX_TURNS:
        bases = [color.to_oklch(hex_) for hex_ in out]
        for ratio, target in options:
            rotated = [
                color.with_contrast_toward(
                    color.from_oklch(L, C, (H + GOLDEN_ANGLE * turn) % 360.0),
                    background,
                    ratio,
                    target,
                )
                for L, C, H in bases
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
                break
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
