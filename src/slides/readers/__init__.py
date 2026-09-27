import pathlib
from slides.model import Deck


def detect(target: str | pathlib.Path | None) -> str:
    if target is None:
        return "live"
    path = pathlib.Path(target)
    if path.suffix == ".key":
        return "keynote"
    if path.suffix == ".pptx":
        return "pptx"
    if path.is_dir() and (path / "deck.json").exists():
        return "deckwerk"
    raise ValueError("%s is not a deck" % (path,))


def read(
    target: str | pathlib.Path | None,
    via_deckwerk: bool = False
) -> Deck:
    kind = detect(target)
    if kind == "live":
        from slides.readers import keynote_live
        return keynote_live.read()
    if kind == "keynote":
        from slides.readers import keynote_file
        return keynote_file.read(target, via_deckwerk=via_deckwerk)
    if kind == "pptx":
        from slides.readers import pptx
        return pptx.read(target)
    from slides.readers import deckwerk
    return deckwerk.read(target)
