import copy
import random
import shutil
import pathlib
import tempfile
from slides import color
from slides.keynote import math

# CSS text-align to TSWP's paragraph alignment values.
ALIGNMENT = {"left": "TATvalue0", "right": "TATvalue1", "center": "TATvalue2", "justify": "TATvalue3"}
NULL_CHARACTER_STYLE = "character-style-null"
# DeckWerk's one build action, as the build Keynote users reach for first.
EFFECTS = {"appear": "apple:dissolve"}
BUILD_DURATION = 0.4
BUILD_TYPE = 8
CHUNK_TYPE = 153


def finish(
    deck: pathlib.Path,
    slides: list[dict]
) -> None:
    # What Keynote's scripting cannot set, written into the saved .key:
    # each slide's background, and each text box's alignment and inline runs.
    # slides[n] is {"background", "texts": [{"text", "align", "runs"}]}, texts in
    # the order the boxes were made. Rewrites the deck in place.
    with tempfile.TemporaryDirectory(prefix="slides-finish-") as staging:
        work = pathlib.Path(staging)
        unpacked = work / "deck"
        math.unpack_deck(math.zipped(deck, work), unpacked)
        Finisher(unpacked).run(slides)
        if deck.is_dir():
            shutil.rmtree(deck)
        else:
            deck.unlink()
        math.repack_deck(unpacked, deck)


class Finisher:
    def __init__(self, work: pathlib.Path) -> None:
        self.index = work / "Index"
        self.document = math.load(self.index / "Document.iwa.yaml")
        self.metadata = math.load(self.index / "Metadata.iwa.yaml")
        self.stylesheet = math.load(self.index / "DocumentStylesheet.iwa.yaml")
        self.package = self.metadata["chunks"][0]["archives"][0]["objects"][0]
        self.next_id = math.first_free_id(self.index, self.package)
        self.stylesheet_id = component(self.package, "DocumentStylesheet")["identifier"]
        self.cache: dict[tuple, str] = {}

    def run(self, slides: list[dict]) -> None:
        archives = {a["header"]["identifier"]: a for a in chunk(self.document)}
        show = next(a for a in chunk(self.document) if kind(a) == "KN.ShowArchive")
        nodes = [ref["identifier"] for ref in show["objects"][0]["slideTree"]["slides"]]
        files = self._slide_files()
        for node, want in zip(nodes, slides):
            slide_id = archives[node]["objects"][0]["slide"]["identifier"]
            clicks = self._slide(slide_id, files[slide_id], want)
            if clicks is not None:
                flags = archives[node]["objects"][0]
                flags.update({"hasBuilds": True, "hasExplicitBuilds": True, "buildEventCount": clicks})
        self.package["lastObjectIdentifier"] = str(self.next_id - 1)
        math.dump(self.document, self.index / "Document.iwa.yaml")
        math.dump(self.metadata, self.index / "Metadata.iwa.yaml")
        math.dump(self.stylesheet, self.index / "DocumentStylesheet.iwa.yaml")

    def _slide_files(self) -> dict[str, pathlib.Path]:
        # Keynote names slide files by component, not always by slide id.
        files = {}
        for path in self.index.glob("Slide*.iwa.yaml"):
            for archive in chunk(math.load(path)):
                if kind(archive) == "KN.SlideArchive":
                    files[archive["header"]["identifier"]] = path
        return files

    def _slide(
        self,
        slide_id: str,
        path: pathlib.Path,
        want: dict
    ) -> int | None:
        entry = next(c for c in self.package["components"] if c["identifier"] == slide_id)
        data = math.load(path)
        by_id = {a["header"]["identifier"]: a for a in chunk(data)}
        archive = next(a for a in chunk(data) if kind(a) == "KN.SlideArchive")
        body = archive["objects"][0]
        parent = body["style"]["identifier"]
        fill = {"slideProperties": {"fill": {"color": _colour(want["background"])}}}
        style = self._child(parent, fill, ("slide", parent, want["background"]))
        body["style"] = {"identifier": style}
        _swap(archive, parent, style)
        used = [style]
        boxes = [
            by_id[ref["identifier"]]
            for ref in body.get("drawablesZOrder", [])
            if ref["identifier"] in by_id and by_id[ref["identifier"]]["objects"][0].get("isTextBox")
        ]
        for box, text in zip(boxes, want["texts"]):
            storage = by_id[box["objects"][0]["ownedStorage"]["identifier"]]
            used += self._paragraphs(storage, _paragraph_properties(text))
            used += self._runs(storage, text["runs"])
        external = entry.setdefault("externalReferences", [])
        known = set(e.get("objectIdentifier") for e in external)
        external.extend({"componentIdentifier": self.stylesheet_id, "objectIdentifier": i} for i in dict.fromkeys(used) if i not in known)
        clicks = self._builds(data, archive, entry, want)
        math.dump(data, path)
        return clicks

    def _builds(
        self,
        data: dict,
        archive: dict,
        entry: dict,
        want: dict
    ) -> int | None:
        # Drawables stack in the order the builder made them: images, then
        # text boxes, then tables. That order names each one's DeckWerk id.
        body = archive["objects"][0]
        body.setdefault("builds", [])
        body.setdefault("buildChunks", [])
        if not want.get("builds") and not body["buildChunks"]:
            return None
        made = want["images"] + want["texts"] + want["tables"]
        drawables = [ref["identifier"] for ref in body.get("drawablesZOrder", [])]
        if len(made) != len(drawables):
            raise ValueError("slide has %d drawables but %d were made" % (len(drawables), len(made)))
        by_id = {a["header"]["identifier"]: a for a in data["chunks"][0]["archives"]}
        # Keynote gives each movie it makes a Start Movie build on click; one
        # DeckWerk autoplays starts with the slide instead.
        source = dict(zip(drawables, made))
        for ref in body["buildChunks"]:
            own = by_id[ref["identifier"]]["objects"][0]
            if source[by_id[own["build"]["identifier"]]["objects"][0]["drawable"]["identifier"]].get("autoplay"):
                own["automatic"] = True
        info = archive["header"]["messageInfos"][0].setdefault("objectReferences", [])
        uuids = entry.setdefault("objectUuidMapEntries", [])
        for step in want["builds"]:
            targets = [d for d in drawables if source[d].get("id") == step["target"]]
            for index, drawable in enumerate(targets):
                trigger = step["trigger"] if index == 0 else "withPrev"
                build, chunk = self._build_pair(drawable, step, trigger, kind(by_id[drawable]) == "TSWP.ShapeInfoArchive")
                data["chunks"][0]["archives"].extend([build, chunk])
                body["builds"].append({"identifier": build["header"]["identifier"]})
                body["buildChunks"].append({"identifier": chunk["header"]["identifier"]})
                info.extend([build["header"]["identifier"], chunk["header"]["identifier"]])
                # A chunk finds its build by the build's UUID; chunks have none.
                uuids.append({"identifier": build["header"]["identifier"], "uuid": chunk["objects"][0]["buildId"]})
                by_id[chunk["header"]["identifier"]] = chunk
        return sum(not by_id[ref["identifier"]]["objects"][0]["automatic"] for ref in body["buildChunks"])

    def _build_pair(
        self,
        drawable: str,
        step: dict,
        trigger: str,
        text: bool
    ) -> tuple[dict, dict]:
        build_id, chunk_id = str(self.next_id), str(self.next_id + 1)
        self.next_id += 2
        identity = _uuid()
        build = {
            "header": {"_pbtype": "TSP.ArchiveInfo", "identifier": build_id, "messageInfos": [{"type": BUILD_TYPE, "version": [1, 0, 5]}]},
            "objects": [{
                "_pbtype": "KN.BuildArchive",
                "drawable": {"identifier": drawable},
                "delivery": "All at Once",
                "duration": 0.0,
                "chunkIdSeed": 1,
                "attributes": {
                    "eventTrigger": 1,
                    "ChartRotation3D": 60.0,
                    "animationAttributes": {
                        "animationType": "In",
                        "effect": EFFECTS.get(step["effect"], EFFECTS["appear"]),
                        "duration": BUILD_DURATION,
                        "delay": 0.0,
                        "randomNumberSeed": random.getrandbits(31),
                        "writingDirectionIsRtl": False,
                    },
                },
            }],
        }
        chunk = {
            "header": {"_pbtype": "TSP.ArchiveInfo", "identifier": chunk_id, "messageInfos": [{"type": CHUNK_TYPE, "version": [1, 0, 5]}]},
            "objects": [{
                "_pbtype": "KN.BuildChunkArchive",
                "build": {"identifier": build_id},
                "automatic": trigger != "click",
                # On click and after the previous build both follow it;
                # starting with the previous one does not.
                "referent": trigger != "withPrev",
                "delay": float(step.get("delay") or 0.0),
                "duration": BUILD_DURATION,
                "buildChunkIdentifier": {"buildChunkId": 1, "buildId": identity},
                "buildId": identity,
            }],
        }
        if text:
            build["objects"][0]["attributes"].update({"customDeliveryOption": "kDeliveryOptionForward", "customTextDelivery": "kTextDeliveryByObject"})
        return build, chunk

    def _paragraphs(
        self,
        storage: dict,
        props: dict
    ) -> list[str]:
        made = []
        signature = tuple(sorted((k, str(v)) for k, v in props.items()))
        for entry in storage["objects"][0]["tableParaStyle"]["entries"]:
            parent = entry.get("object", {}).get("identifier")
            if parent is None:
                continue
            child = self._child(parent, {"paraProperties": props}, ("paragraph", parent, signature))
            entry["object"] = {"identifier": child}
            _swap(storage, parent, child)
            made.append(child)
        return made

    def _runs(
        self,
        storage: dict,
        runs: list[dict]
    ) -> list[str]:
        # Inline spans as character-style runs, at UTF-16 offsets into the text
        # Keynote actually stored.
        if not runs:
            return []
        body = storage["objects"][0]
        text = "".join(body.get("text") or [])
        parent = self._null_character_style()
        entries: list[dict] = []
        made = []
        for run in sorted(runs, key=lambda r: r["start"]):
            start, end = math.utf16_len(text[:run["start"]]), math.utf16_len(text[:run["end"]])
            if end <= start:
                continue
            props = _character_properties(run["style"])
            key = ("run", tuple(sorted((k, str(v)) for k, v in props.items())))
            child = self._child(parent, {"charProperties": props}, key)
            made.append(child)
            if entries and entries[-1]["characterIndex"] == start and "object" not in entries[-1]:
                entries.pop()
            entries.append({"characterIndex": start, "object": {"identifier": child}})
            entries.append({"characterIndex": end})
        if entries and entries[0]["characterIndex"] > 0:
            entries.insert(0, {"characterIndex": 0})
        body["tableCharStyle"] = {"entries": entries}
        info = storage["header"]["messageInfos"][0]
        refs = info.setdefault("objectReferences", [])
        refs.extend(i for i in dict.fromkeys(made) if i not in refs)
        return made

    def _null_character_style(self) -> str:
        for archive in chunk(self.stylesheet):
            if kind(archive) == "TSWP.CharacterStyleArchive":
                if archive["objects"][0].get("super", {}).get("styleIdentifier") == NULL_CHARACTER_STYLE:
                    return archive["header"]["identifier"]
        raise ValueError("the stylesheet has no null character style")

    def _child(
        self,
        parent: str,
        changes: dict,
        key: tuple
    ) -> str:
        # An anonymous child of an existing style, registered the way Keynote
        # registers the overrides it makes itself. Identical overrides share one.
        if key in self.cache:
            return self.cache[key]
        archives = chunk(self.stylesheet)
        child = copy.deepcopy(next(a for a in archives if a["header"]["identifier"] == parent))
        ident = str(self.next_id)
        self.next_id += 1
        child["header"]["identifier"] = ident
        base = child["objects"][0]["super"]
        base.pop("name", None)
        base.pop("styleIdentifier", None)
        base["parent"] = {"identifier": parent}
        base["isVariation"] = True
        for group, values in changes.items():
            child["objects"][0].setdefault(group, {}).update(values)
        refs = child["header"]["messageInfos"][0].setdefault("objectReferences", [])
        if parent not in refs:
            refs.append(parent)
        archives.append(child)
        sheet = next(a for a in archives if kind(a) == "TSS.StylesheetArchive")
        sheet["objects"][0]["styles"].append({"identifier": ident})
        family = sheet["objects"][0].setdefault("parentToChildrenStyleMap", [])
        entry = next((e for e in family if e["parent"]["identifier"] == parent), None)
        if entry is None:
            entry = {"parent": {"identifier": parent}, "children": []}
            family.append(entry)
        entry["children"].append({"identifier": ident})
        sheet["header"]["messageInfos"][0].setdefault("objectReferences", []).append(ident)
        uuids = component(self.package, "DocumentStylesheet").setdefault("objectUuidMapEntries", [])
        uuids.append({"identifier": ident, "uuid": {"lower": str(random.getrandbits(64)), "upper": str(random.getrandbits(64))}})
        self.cache[key] = ident
        return ident


def _paragraph_properties(text: dict) -> dict:
    props = {"alignment": ALIGNMENT.get(text.get("align", "left"), ALIGNMENT["left"])}
    if text.get("lineSpacing"):
        props["lineSpacing"] = {"amount": float(text["lineSpacing"])}
    if text.get("spaceAfter"):
        props["spaceAfter"] = float(text["spaceAfter"])
    return props


def _character_properties(style: dict) -> dict:
    props = {}
    if "color" in style:
        props["fontColor"] = _colour(style["color"])
    if "font" in style:
        props["fontName"] = style["font"]
    if "size" in style:
        props["fontSize"] = float(style["size"])
    return props


def _swap(
    archive: dict,
    old: str,
    new: str
) -> None:
    info = archive["header"]["messageInfos"][0]
    refs = info.get("objectReferences", [])
    info["objectReferences"] = [new if r == old else r for r in refs] if old in refs else refs + [new]


def component(
    package: dict,
    name: str
) -> dict:
    # Slides carry a locator; the document's named parts only a preferred one.
    return next(c for c in package["components"] if (c.get("locator") or c.get("preferredLocator")) == name)


def chunk(data: dict) -> list:
    return data["chunks"][0]["archives"]


def kind(archive: dict) -> str:
    return archive["objects"][0].get("_pbtype", "") if archive.get("objects") else ""


def _uuid() -> dict:
    return {"lower": str(random.getrandbits(64)), "upper": str(random.getrandbits(64))}


def _colour(value: str) -> dict:
    red, green, blue = color.to_rgb(value)
    return {"a": 1.0, "r": red, "g": green, "b": blue, "model": "rgb", "rgbspace": "srgb"}
