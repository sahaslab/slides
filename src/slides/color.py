import math

LUMA = (0.2126, 0.7152, 0.0722)
HALVINGS = 24


def to_rgb(value: str) -> tuple[float, float, float]:
    text = value.lstrip("#")
    return tuple(int(text[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def to_hex(
    r: float,
    g: float,
    b: float,
) -> str:
    return "#%02x%02x%02x" % tuple(
        max(0, min(255, int(round(c * 255.0)))) for c in (r, g, b)
    )


def to_oklab(value: str) -> tuple[float, float, float]:
    r, g, b = (_linear(c) for c in to_rgb(value))
    l = _cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b)
    m = _cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b)
    s = _cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b)
    return (
        0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
        1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
        0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s,
    )


def from_oklab(
    L: float,
    a: float,
    b: float,
) -> str:
    r, g, b_ = _oklab_to_linear(L, a, b)
    return to_hex(_srgb(r), _srgb(g), _srgb(b_))


def to_oklch(value: str) -> tuple[float, float, float]:
    L, a, b = to_oklab(value)
    return L, math.hypot(a, b), math.degrees(math.atan2(b, a)) % 360.0


def from_oklch(
    L: float,
    C: float,
    H: float,
) -> str:
    radians = math.radians(H)
    return from_oklab(L, C * math.cos(radians), C * math.sin(radians))


def luminance(value: str) -> float:
    return sum(k * _linear(c) for k, c in zip(LUMA, to_rgb(value)))


def contrast(
    one: str,
    other: str,
) -> float:
    a, b = luminance(one), luminance(other)
    high, low = max(a, b), min(a, b)
    return (high + 0.05) / (low + 0.05)


def contrast_extreme(against: str) -> float:
    # Which of pure white (1.0) or pure black (0.0) has more contrast
    # headroom against a background. Luminance and contrast are not
    # symmetric around 0.5 (WCAG's +0.05 offset moves the crossover to
    # luminance about 0.179), so a mid-grey like #767676..#bcbcbc can
    # contrast better against black despite its own luminance being under
    # 0.5.
    return 1.0 if contrast("#ffffff", against) >= contrast("#000000", against) else 0.0


def delta_e(
    one: str,
    other: str,
) -> float:
    first, second = to_oklab(one), to_oklab(other)
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(first, second)))


def mix(
    one: str,
    other: str,
    amount: float,
) -> str:
    first, second = to_oklab(one), to_oklab(other)
    return from_oklab(*[x + (y - x) * amount for x, y in zip(first, second)])


def with_contrast(
    colour: str,
    against: str,
    ratio: float,
) -> str:
    return with_contrast_toward(colour, against, ratio, contrast_extreme(against))


def with_contrast_toward(
    colour: str,
    against: str,
    ratio: float,
    target: float,
) -> str:
    # Pushes colour's lightness toward target (1.0 white, 0.0 black) until
    # it clears ratio against against, refitting chroma to the sRGB gamut
    # at each step (clamping r/g/b independently would shift the hue by
    # several degrees instead).
    if contrast(colour, against) >= ratio:
        return colour
    L, C, H = to_oklch(colour)
    low, high = L, target
    best = from_oklch(target, _fit_chroma(target, C, H), H)
    # Binary search on lightness: contrast is monotone as L moves away from
    # the ground, so HALVINGS halvings land within a rounding step of the
    # boundary.
    for _ in range(HALVINGS):
        middle = (low + high) / 2.0
        candidate = from_oklch(middle, _fit_chroma(middle, C, H), H)
        if contrast(candidate, against) >= ratio:
            best = candidate
            high = middle
        else:
            low = middle
    return best


def _oklab_to_linear(
    L: float,
    a: float,
    b: float,
) -> tuple[float, float, float]:
    l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3
    return (
        4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
        -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
        -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s,
    )


def _in_gamut(
    L: float,
    C: float,
    H: float,
) -> bool:
    radians = math.radians(H)
    r, g, b = _oklab_to_linear(L, C * math.cos(radians), C * math.sin(radians))
    return 0.0 <= r <= 1.0 and 0.0 <= g <= 1.0 and 0.0 <= b <= 1.0


def _fit_chroma(
    L: float,
    C: float,
    H: float,
) -> float:
    if _in_gamut(L, C, H):
        return C
    low, high = 0.0, C
    for _ in range(HALVINGS):
        middle = (low + high) / 2.0
        if _in_gamut(L, middle, H):
            low = middle
        else:
            high = middle
    return low


def _linear(c: float) -> float:
    if c <= 0.04045:
        return c / 12.92
    return ((c + 0.055) / 1.055) ** 2.4


def _srgb(c: float) -> float:
    c = max(0.0, min(1.0, c))
    if c <= 0.0031308:
        return c * 12.92
    return 1.055 * (c ** (1 / 2.4)) - 0.055


def _cbrt(x: float) -> float:
    return math.copysign(abs(x) ** (1 / 3), x)
