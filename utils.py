"Various simple utility functions."

import constants
from translator import Translator

Tx = Translator(constants.TRANSLATIONS_FILE)

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

