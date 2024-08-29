"Constants."

import functools
import os

VERSION = (0, 1, 0)
__version__ = ".".join([str(n) for n in VERSION])


DEFAULT_LANGUAGES = ("sv-SE", "en-GB", "en-US")

MARKDOWN_EXT = ".md"
CONFIG_FILENAME = "config.yaml"
ARCHIVE_DIRNAME = "au_archive"
assert os.extsep not in ARCHIVE_DIRNAME
REFERENCES_DIRNAME = "au_references"
assert os.extsep not in REFERENCES_DIRNAME
TRANSLATIONS_FILE = "translations.csv"

DATETIME_ISO_FORMAT = "%Y-%m-%d %H:%M:%S"
MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}
EM_DASH = "\u2014"


@functools.total_ordering
class Status:
    @classmethod
    def lookup(cls, name, default=None):
        return STATUS_LOOKUP.get(name) or default

    def __init__(self, name, ordinal, color):
        self.name = name
        self.ordinal = ordinal
        self.color = color

    def __str__(self):
        return self.name.capitalize()

    def __repr__(self):
        return self.name

    def __eq__(self, other):
        return self.name == other.name

    def __ne__(self, other):
        return other is None or self.name != other.name

    def __lt__(self, other):
        return self.ordinal < other.ordinal


STARTED = Status("started", 0, "gray")
OUTLINE = Status("outline", 1, "salmon")
INCOMPLETE = Status("incomplete", 2, "tomato")
DRAFT = Status("draft", 3, "crimson")
WRITTEN = Status("written", 4, "dodgerblue")
REVISED = Status("revised", 5, "blue")
DONE = Status("done", 6, "forestgreen")
PROOFS = Status("proofs", 7, "yellowgreen")
FINAL = Status("final", 8, "black")
STATUSES = (STARTED, OUTLINE, INCOMPLETE, DRAFT, WRITTEN, REVISED, DONE, PROOFS, FINAL)
STATUS_LOOKUP = dict([(s.name, s) for s in STATUSES])

REFERENCE_MAX_AUTHORS = 5
ARTICLE = "article"
BOOK = "book"
LINK = "link"
DOI = "https://doi.org/{value}"
PUBMED = "https://pubmed.ncbi.nlm.nih.gov/{value}"
ISBN = "https://isbnsearch.org/isbn/{value}"
