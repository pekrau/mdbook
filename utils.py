"Various simple utility functions."

import constants
import latex_utf8
from translator import Translator

Tx = Translator(constants.TRANSLATIONS_FILEPATH)

def short_name(name):
    "Return the person name in short form; given names as initials."
    parts = [p.strip() for p in name.split(",")]
    if len(parts) == 1:
        return name
    initials = [p.strip()[0] for p in parts.pop().split(" ")]
    parts.append("".join([f"{i}." for i in initials]))
    return ", ".join(parts)

def thousands(i):
    return f"{i:,}".replace(",", ".")

def cleanup(value):
    "Convert LaTeX characters to UTF-8, remove newlines and normalize blanks."
    return latex_utf8.from_latex_to_utf8(" ".join(value.split()))
