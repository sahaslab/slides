import collections
from dataclasses import dataclass, field
from slides import color
from slides.model import ColorUse, Deck

NEUTRAL_CHROMA = 0.04
ACCENT_CHROMA = 0.05
ACCENT_CONTRAST = 3.0
TEXT_CONTRAST = 4.5
DUPLICATE = 0.06


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


def extract(deck: Deck, accents: int = 6) -> DeckTheme:
    candidates = list(deck.colors)
    background = _background(deck, candidates)
    foreground = _foreground(candidates, background)
    return DeckTheme(
        background=background,
        foreground=foreground,
        muted=_muted(candidates, background, foreground),
        grid=_grid(candidates, background, foreground),
        accents=_accents(candidates, background, accents),
        fonts=dict(deck.fonts),
        source=deck.source,
    )


def _background(deck: Deck, candidates: list[ColorUse]) -> str:
    explicit = [s.background for s in deck.slides if s.background]
    if explicit:
        return collections.Counter(explicit).most_common(1)[0][0]
    neutral = [c for c in candidates if color.to_oklch(c.hex)[1] < NEUTRAL_CHROMA]
    pool = neutral or candidates
    if not pool:
        return "#ffffff"
    return max(pool, key=lambda c: c.weight).hex


def _foreground(candidates: list[ColorUse], background: str) -> str:
    text = [c for c in candidates if c.kind == "text"] or candidates
    if not text:
        return color.with_contrast(
            "#ffffff" if color.luminance(background) < 0.5 else "#000000",
            background,
            TEXT_CONTRAST,
        )
    clearing = [c for c in text if color.contrast(c.hex, background) >= TEXT_CONTRAST]
    if clearing:
        return max(
            clearing,
            key=lambda c: (c.weight, color.contrast(c.hex, background)),
        ).hex
    best = max(text, key=lambda c: color.contrast(c.hex, background))
    return color.with_contrast(best.hex, background, TEXT_CONTRAST)


def _muted(candidates: list[ColorUse], background: str, foreground: str) -> str:
    ceiling = color.contrast(foreground, background)
    band = [
        c for c in candidates
        if 2.0 <= color.contrast(c.hex, background) < ceiling
    ]
    if not band:
        return color.mix(foreground, background, 0.55)
    target_hue = color.to_oklch(foreground)[2]
    return min(band, key=lambda c: _hue_gap(color.to_oklch(c.hex)[2], target_hue)).hex


def _grid(candidates: list[ColorUse], background: str, foreground: str) -> str:
    band = [c for c in candidates if 1.1 <= color.contrast(c.hex, background) < 2.0]
    if not band:
        return color.mix(foreground, background, 0.85)
    return max(band, key=lambda c: c.weight).hex


def _accents(candidates: list[ColorUse], background: str, count: int) -> list[str]:
    chromatic = [c for c in candidates if color.to_oklch(c.hex)[1] >= ACCENT_CHROMA]
    chromatic.sort(key=lambda c: -c.weight)
    clusters: list[list[str]] = []
    for candidate in chromatic:
        raised = color.with_contrast(candidate.hex, background, ACCENT_CONTRAST)
        _absorb(clusters, raised)
    kept = [cluster[0] for cluster in clusters]
    spread = _spread(kept, count)
    return _pad(spread, background, count)


def _absorb(clusters: list[list[str]], raised: str) -> None:
    # Single-link clustering: a candidate joins a cluster if it is near ANY
    # member of it, not just the first-kept leader. A preset gradient family
    # (e.g. #00a2ff..#1fa3ff) is a chain of near-duplicates whose endpoints
    # can exceed DUPLICATE even though each step does not; requiring the
    # candidate to clear every kept leader (complete-link) leaves that chain
    # split into two accents instead of collapsing to one.
    for cluster in clusters:
        if any(color.delta_e(raised, member) < DUPLICATE for member in cluster):
            cluster.append(raised)
            return
    clusters.append([raised])


def _spread(accents: list[str], count: int) -> list[str]:
    if len(accents) <= count:
        return accents
    chosen = [accents[0]]
    remaining = accents[1:]
    while len(chosen) < count and remaining:
        pick = max(
            remaining,
            key=lambda c: min(
                _hue_gap(color.to_oklch(c)[2], color.to_oklch(p)[2]) for p in chosen
            ),
        )
        chosen.append(pick)
        remaining.remove(pick)
    return chosen


def _pad(accents: list[str], background: str, count: int) -> list[str]:
    # Derive the shortfall by rotating the deck's own hues, never from a
    # palette shipped with the tool. At each rotation turn every base hue is
    # a candidate; the one that maximises the minimum hue gap to everything
    # already kept is taken. Fixing the rotation to a single per-base offset
    # (rather than picking for spread) can walk a rotated hue right back
    # into a neighbourhood another accent already occupies.
    if not accents:
        seed = color.with_contrast(
            color.from_oklch(0.75, 0.15, 150.0), background, ACCENT_CONTRAST
        )
        accents = [seed]
    out = list(accents)
    bases = [color.to_oklch(hex_) for hex_ in accents]
    step = 360.0 / max(count, 1)
    turn = 1
    while len(out) < count and turn <= count * 6:
        candidates = [
            color.with_contrast(
                color.from_oklch(L, C, (H + step * turn) % 360.0),
                background,
                ACCENT_CONTRAST,
            )
            for L, C, H in bases
        ]
        fresh = [
            c for c in candidates
            if all(color.delta_e(c, other) >= DUPLICATE for other in out)
        ]
        if fresh:
            out.append(max(
                fresh,
                key=lambda c: min(
                    _hue_gap(color.to_oklch(c)[2], color.to_oklch(o)[2]) for o in out
                ),
            ))
        turn += 1
    return out[:count]


def _hue_gap(one: float, other: float) -> float:
    gap = abs(one - other) % 360.0
    return min(gap, 360.0 - gap)
