"Various simple utility functions."

import csv
import datetime
import hashlib
import json
import os
import string
import unicodedata

import requests

import constants
import latex_utf8


SAFE_CHARACTERS = set(string.ascii_letters + string.digits)


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


def cleanup_latex(value):
    "Convert LaTeX characters to UTF-8, remove newlines and normalize blanks."
    return latex_utf8.from_latex_to_utf8(" ".join(value.split()))


def nameify(title):
    "Make name (lowercase letters, digits, ASCII-only) out of a title."
    result = unicodedata.normalize("NFKD", title).encode("ASCII", "ignore")
    return "".join([c.lower() if c in SAFE_CHARACTERS else "-"
                    for c in result.decode("utf-8")])

def get_digest(c):
    "Return the digest instance having processed frontmatter and content."
    result = hashlib.md5()
    frontmatter = c.frontmatter.copy()
    frontmatter.pop("digest", None) # Necessary!
    result.update(json.dumps(frontmatter, sort_keys=True).encode("utf-8"))
    result.update(c.content.encode("utf-8"))
    return result

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

def get_state_remote(bid=None):
    "Get the remote site state, optionally for the given bid."
    if "MDBOOK_UPDATE_SITE" not in os.environ:
        raise ValueError("remote update site undefined; missing MDBOOK_UPDATE_SITE")
    if "MDBOOK_UPDATE_APIKEY" not in os.environ:
        raise ValueError("remote update apikey undefined; missing MDBOOK_UPDATE_APIKEY")
    url = os.environ["MDBOOK_UPDATE_SITE"].rstrip("/")
    if bid:
        url += "/state"
    headers = dict(apikey=os.environ["MDBOOK_UPDATE_APIKEY"])
    response = requests.get(url, headers=headers)
    if response.status_code == 404:
        return None
    elif response.status_code != 200:
        raise ValueError(f"remote {url} response error: {response.status_code}; {response.content}")
    return response.json()


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
    for s in ["Uvö",
              "Västerby 5:256",
              "Är detta en såpass bra rubrik?"]:
        print(s, nameify(s))
