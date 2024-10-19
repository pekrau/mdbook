"Various simple utility functions."

import csv
import datetime
import json
import os
import time

import constants
import latex_utf8


def get_config():
    """Get the local instance config file, if any.
    This is only for local instances, not for web instances.
    """
    try:
        with open(os.path.join(os.path.dirname(__file__), "config.json")) as infile:
            return json.load(infile)
    except FileNotFoundError:
        return {}


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


def check_disallowed_characters(title):
    """Raise ValueError if title contains any disallowed characters;
    those with special meaning in file system.
    """
    disalloweds = [os.extsep, os.sep]
    if os.altsep:
        disalloweds.append(os.altsep)
    for disallowed in disalloweds:
        if disallowed in title:
            raise ValueError(f"The title may not contain the character '{disallowed}'.")


def timestr(filepath=None, localtime=True, display=True, safe=False):
    "Return time string for modification date of the given file, or now."
    if filepath:
        timestamp = os.path.getmtime(filepath)
        if localtime:
            result = datetime.datetime.fromtimestamp(timestamp)
        else:
            result = datetime.datetime.fromtimestamp(timestamp, datetime.UTC)
    elif localtime:
        result = datetime.datetime.now()
    else:
        result = datetime.datetime.now(datetime.UTC)
    result = result.strftime(constants.DATETIME_ISO_FORMAT)
    if not display:
        result = result.replace(" ", "T") + "Z"
    if safe:
        result = result.replace(" ", "_").replace(":", "-")
    return result

def tolocaltime(utctime):
    "Convert a time string in UTC to local time."
    mytz = datetime.datetime.now(datetime.timezone.utc).astimezone().tzinfo
    lt = datetime.datetime.fromisoformat(utctime).astimezone(mytz)
    return lt.strftime(constants.DATETIME_ISO_FORMAT)

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
    t = "2024-10-19T15:14:03Z"
    print(t)
    print(localtime(t))
    # for s in [
    #     timestr(),
    #     timestr(filepath="README.md"),
    #     timestr(display=False),
    #     timestr(filepath="README.md", display=False),
    #     timestr(localtime=False),
    #     timestr(filepath="README.md", localtime=False, display=False),
    # ]:
    #     print(s, "   ", datetime.datetime.fromisoformat(s))
    # import constants

    # tr = Translator(constants.TRANSLATIONS_FILE)
    # print(str(tr))
    # print(tr.languages)
    # for term in ["item", "section"]:
    #     print(term, tr(term))
