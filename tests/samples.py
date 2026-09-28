import os
import pathlib

# Real decks for the regression tests that only a real file can exercise. Point
# SLIDES_SAMPLE_DECKS at a folder holding them; those tests skip without it.
SAMPLES = pathlib.Path(os.environ.get("SLIDES_SAMPLE_DECKS", "")).expanduser()
