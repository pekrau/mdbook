"Various simple utility functions."

import csv
import os.path
import time

import constants
import latex_utf8


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


def timestr(filepath=None):
    if filepath:
        result = time.localtime(os.path.getmtime(filepath))
    else:
        result = time.localtime()
    return time.strftime(constants.DATETIME_ISO_FORMAT, result)


class Translator:
    "Simple translation of words and phrases from one language to another."

    def __init__(self, translation_csv_file, source=None, target=None):
        """The CSV file must have one column per language.
        The header of each column specifies the name of the language.
        """
        with open(translation_csv_file) as infile:
            self.terms = list(csv.DictReader(infile))
        self.source = source or tuple(self.terms[0].keys())[0]
        self.target = target or tuple(self.terms[0].keys())[1]
        self.set_translation(self.source, self.target)

    def __str__(self):
        return f"{self.__class__.__name__} {self.source} -> {self.target}"

    @property
    def languages(self):
        return tuple(self.terms[0].keys())

    def set_translation(self, source, target):
        if source not in self.terms[0]:
            raise ValueError(f"language 'source' not in the translation data.")
        if target not in self.terms[0]:
            raise ValueError(f"language 'target' not in the translation data.")
        self.translation = {}
        for term in self.terms:
            self.translation[term[source]] = term[target]
            self.translation[term[source].lower()] = term[target].lower()
            self.translation[term[source].upper()] = term[target].upper()
            self.translation[term[source].capitalize()] = term[target].capitalize()

    def __call__(self, term):
        return self.translation.get(str(term), term)


Tx = Translator(constants.TRANSLATIONS_FILEPATH)


if __name__ == "__main__":
    import constants

    tr = Translator(constants.TRANSLATIONS_FILE)
    print(str(tr))
    print(tr.languages)
    for term in ["item", "section"]:
        print(term, tr(term))
