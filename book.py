"Markdown book texts in files and directories."

from icecream import ic

import copy
import datetime
import io
import os
import re
import tarfile
import time
from urllib.parse import quote as urlquote

import yaml

import constants
import markdown

FRONTMATTER = re.compile(r"^---([\n\r].*?[\n\r])---[\n\r](.*)$", re.DOTALL)


def read_frontmatter(content):
    "Return the frontmatter as dictionary and the remaining content."
    match = FRONTMATTER.match(content)
    if match:
        return yaml.safe_load(match.group(1)), content[match.start(2) :]
    else:
        return {}, content


def write_frontmatter(outfile, frontmatter):
    if not frontmatter:
        return
    outfile.write("---\n")
    outfile.write(yaml.dump(frontmatter, allow_unicode=True))
    outfile.write("---\n")


class Book:
    "Root container for Markdown book texts in files and directories."

    def __init__(self, absdirpath):
        self.absdirpath = absdirpath
        self.read()

    def __str__(self):
        return self.title

    def __repr__(self):
        return f"Book('{self}')"

    def __len__(self):
        "Number of characters in Markdown content in all texts."
        return sum([len(i) for i in self.all_texts]) + len(self.index)

    def __bool__(self):
        "Always True; not dependent on len."
        return True

    def __getitem__(self, fullname):
        return self.lookup[fullname]

    def read(self):
        "Read all items from files. Set up references and indexed lookups."
        try:
            self.index = Text(self, self, "index.md")
        except OSError:
            with open(os.path.join(self.absdirpath, "index.md"), "w") as outfile:
                pass
        self.frontmatter = self.index.frontmatter

        self.items = []
        self.lookup = {}

        # Section and Text instances for directories and files that actually exist.
        for itemname in sorted(os.listdir(self.absdirpath)):
            # Skip emacs temporary edit file.
            if itemname.startswith(".#"):
                continue
            # Do not include 'index.md' file; handled separately.
            if itemname == "index.md":
                continue

            itempath = os.path.join(self.absdirpath, itemname)
            if os.path.isdir(itempath):
                self.items.append(Section(self, self, itemname))

            elif itemname.endswith(constants.MARKDOWN_EXT):
                item = Text(self, self, itemname)
                if not item.get("exclude"):
                    self.items.append(item)
            else:
                pass

        for item in self.all_items:
            self.lookup[item.fullname] = item

        self.references = {}
        for item in self.all_texts:
            self.find_references(item, item.ast)

        self.indexed = {}
        for item in self.all_texts:
            self.find_indexed(item, item.ast)

        # Re-order items according to the 'index.md' file; save if any change.
        original = copy.deepcopy(self.frontmatter)
        self.set_items_order(self, self.frontmatter.get("items", []))
        self.frontmatter["items"] = self.get_items_order(self)
        if self.frontmatter != original:
            self.index.write()

    def set_items_order(self, container, items_order):
        original = dict([i.title, i] for i in container.items)
        container.items = []
        for ordered in items_order:
            try:
                item = original.pop(ordered["title"])
            except KeyError:
                pass
            else:
                container.items.append(item)
                if isinstance(item, Section):
                    self.set_items_order(item, ordered.get("items", []))
        # Append items not referenced in the frontmatter 'items'.
        container.items.extend(original.values())

    def get_items_order(self, container):
        result = []
        for item in container.items:
            if isinstance(item, Section):
                result.append(dict(items=self.get_items_order(item), title=item.title))
            else:
                result.append(dict(title=item.title))
        return result

    @property
    def abspath(self):
        return self.absdirpath

    @property
    def fullname(self):
        return ""

    @property
    def parent(self):
        return None

    @property
    def level(self):
        return 0

    @property
    def max_level(self):
        return max([i.level for i in self.all_items])

    @property
    def all_items(self):
        "Return list of all sub-items. Self is *not* included."
        result = []
        for item in self.items:
            result.append(item)
            result.extend(item.all_items)
        return result

    @property
    def all_texts(self):
        "Return list of all sub-items that are texts."
        result = []
        for item in self.items:
            result.extend(item.all_texts)
        return result

    @property
    def n_words(self):
        "Approximate number of words in the book."
        return sum([i.n_words for i in self.all_texts]) + self.index.n_words

    @property
    def status(self):
        "Return the lowest status for the sub-items."
        status = constants.FINAL
        for item in self.items:
            status = min(status, item.status)
        return status

    @property
    def is_text(self):
        return False

    @property
    def id(self):
        return os.path.basename(self.absdirpath)

    @property
    def title(self):
        return self.frontmatter.get("title") or os.path.basename(self.absdirpath)

    @title.setter
    def title(self, title):
        self.frontmatter["title"] = title

    @property
    def subtitle(self):
        return self.frontmatter.get("subtitle")

    @subtitle.setter
    def subtitle(self, subtitle):
        self.frontmatter["subtitle"] = subtitle

    @property
    def authors(self):
        return self.frontmatter.get("authors") or []

    @authors.setter
    def authors(self, authors):
        self.frontmatter["authors"] = authors

    @property
    def language(self):
        return self.frontmatter.get("language")

    @language.setter
    def language(self, language):
        self.frontmatter["language"] = language

    @property
    def docx(self):
        return self.frontmatter.get("docx") or {}

    @property
    def pdf(self):
        return self.frontmatter.get("pdf") or {}

    def find_references(self, item, ast):
        try:
            for child in ast["children"]:
                if isinstance(child, str):
                    continue
                if child["element"] == "reference":
                    self.references.setdefault(child["reference"], set()).add(item)
                self.find_references(item, child)
        except KeyError:
            pass

    def find_indexed(self, item, ast):
        try:
            for child in ast["children"]:
                if isinstance(child, str):
                    continue
                if child["element"] == "indexed":
                    self.indexed.setdefault(child["canonical"], set()).add(item)
                self.find_indexed(item, child)
        except KeyError:
            pass

    def get(self, fullname, default=None):
        return self.lookup.get(fullname, default)

    def create_text(self, title, parent=None):
        """Create a new empty text inside the parent section or book.
        Raise ValueError if there is a problem.
        """
        assert parent is None or isinstance(parent, Section)
        check_disallowed_characters(title)
        if parent is None:
            parent = self
        dirpath = os.path.join(parent.abspath, title)
        filepath = dirpath + constants.MARKDOWN_EXT
        if os.path.exists(dirpath) or os.path.exists(filepath):
            raise ValueError(f"The title is already in use within '{parent}'.")
        with open(filepath, "w") as outfile:
            write_frontmatter(outfile, {"status": repr(constants.STATUSES[0])})
        new = Text(self, parent, title)
        parent.items.append(new)
        self.lookup[new.fullname] = new
        self.write_index()
        return new

    def create_section(self, title, parent=None):
        """Create a new empty section inside the parent section or book.
        Raise ValueError if there is a problem.
        """
        assert parent is None or isinstance(parent, Section)
        check_disallowed_characters(title)
        if parent is None:
            parent = self
        dirpath = os.path.join(parent.abspath, title)
        filepath = dirpath + constants.MARKDOWN_EXT
        if os.path.exists(dirpath) or os.path.exists(filepath):
            raise ValueError(f"The title is already in use within '{parent}'.")
        os.mkdir(dirpath)
        new = Section(self, parent, title)
        parent.items.append(new)
        self.lookup[new.fullname] = new
        self.write_index()
        return new

    def delete(self, item):
        "Delete the given item."
        if item.is_section:
            if len(item.items) != 0:
                raise ValueError("Cannot delete non-empty section.")
            os.rmdir(item.abspath)
        else:
            os.remove(item.abspath)
        self.lookup.pop(item.fullname)
        item.parent.items.remove(item)
        self.write_index()

    def write_index(self):
        "Write the updated 'index.md' file."
        self.frontmatter["items"] = self.get_items_order(self)
        self.index.write()

    def archive(self):
        """Write all files for this book to a gzipped tar file.
        Return the BytesIO instance containing the file.
        """
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode="w:gz") as archivefile:
            archivefile.add(self.index.abspath, arcname="index.md")
            for item in self.items:
                archivefile.add(item.abspath, arcname=item.filename(), recursive=True)
        return output

    def check_integrity(self):
        assert os.path.exists(self.abspath), (self, self.abspath)
        assert os.path.isdir(self.abspath), (self, self.abspath)
        assert len(self.lookup) == len(self.all_items), (
            ic(
                len(self.lookup),
                len(self.all_items),
                self.lookup.keys(),
                self.all_items,
            ),
        )
        for item in self.all_items:
            assert item.book is self, (self, item)
            assert isinstance(item, Text) or isinstance(item, Section), (self, item)
            item.check_integrity()
        for text in self.all_texts:
            assert isinstance(text, Text), (self, text)
        # XXX Check that no extra files/dirs exist.


class Item:
    "Abstract class for sections and texts."

    def __init__(self, book, parent, title):
        self.book = book
        self.parent = parent
        self.title = title
        self.read()

    def __str__(self):
        return self.title

    def __repr__(self):
        return f"{self.__class__.__name__}('{self.fullname}')"

    def __bool__(self):
        "Always True; not dependent on len."
        return True

    def read(self):
        "To be implemented by inheriting classes."
        raise NotImplementedError

    @property
    def fullname(self):
        if self.parent is self.book:
            return self.title
        else:
            return os.path.join(self.parent.fullname, self.title)

    @property
    def urlpath(self):
        if self.parent is self.book:
            return urlquote(self.title)
        else:
            return os.path.join(self.parent.urlpath, urlquote(self.title))

    @property
    def level(self):
        result = 0
        parent = self.parent
        while parent is not None:
            result += 1
            parent = parent.parent
        return result

    @property
    def is_text(self):
        return False

    @property
    def is_section(self):
        return False

    @property
    def index(self):
        "The zero-based index of this item among its siblings."
        for result, item in enumerate(self.parent.items):
            if item is self:
                return result

    @property
    def ordinal(self):
        "Tuple of parent's and its own index for sorting purposes."
        result = [self.index + 1]
        parent = self.parent
        while parent is not self.book:
            result.append(parent.index + 1)
            parent = parent.parent
        return tuple(reversed(result))

    @property
    def heading(self):
        "Title preceded by ordinal."
        return f'{".".join([str(i) for i in self.ordinal])}. {self.title}'

    @property
    def prev(self):
        "Previous sibling or None."
        index = self.index
        if index == 0:
            return None
        return self.parent.items[index - 1]

    @property
    def next(self):
        "Next sibling or None."
        try:
            return self.parent.items[self.index + 1]
        except IndexError:
            return None

    @property
    def parentpath(self):
        if self.parent is self.book:
            return ""
        else:
            return self.parent.fullname

    @property
    def chapter(self):
        "Top-level section or text for this item; possibly itself."
        item = self
        while item.parent is not self.book:
            item = item.parent
        return item

    def filename(self, newname=None):
        "To be implemented by inheriting classes."
        raise NotImplementedError

    @property
    def abspath(self):
        return os.path.join(self.parent.abspath, self.filename())

    @property
    def age(self):
        "Get the age of the file."
        now = datetime.datetime.today()
        modified = datetime.datetime.fromtimestamp(os.path.getmtime(self.abspath))
        age = now - modified
        if age.days >= 365.25:
            value = age.days / 365.25
            unit = "yrs"
        elif age.days >= 30.5:
            value = age.days / 30.5
            unit = "mths"
        elif age.days >= 1:
            value = age.days + age.seconds / 86400.0
            unit = "days"
        elif age.seconds >= 3600.0:
            value = age.seconds / 3600.0
            unit = "hrs"
        elif age.seconds >= 60.0:
            value = age.seconds / 60.0
            unit = "mins"
        else:
            value = age.seconds + age.microseconds / 1000000.0
            unit = "secs"
        return f"{value:.0f} {unit}"

    def set_title(self, new):
        """Set title for the item.
        Raise ValueError if any problem.
        """
        if new == self.title:
            return
        if not new:
            raise ValueError("Empty string given for title.")
        check_disallowed_characters(new)
        newabspath = os.path.join(self.parent.abspath, self.filename(new))
        if os.path.exists(newabspath):
            raise ValueError("The title is already in use.")
        items = [self] + self.all_items
        for item in items:
            self.book.lookup.pop(item.fullname)
        oldabspath = self.abspath
        self.title = new
        os.rename(oldabspath, self.abspath)
        for item in items:
            self.book.lookup[item.fullname] = item
        self.book.write_index()

    def up(self):
        "Move this item up in its list of siblings."
        index = self.index
        if index == 0:
            self.parent.items.append(self.parent.items.pop(index))
        else:
            self.parent.items.insert(index - 1, self.parent.items.pop(index))

    def down(self):
        "Move this item down in its list of siblings."
        index = self.index
        if index == len(self.parent.items) - 1:
            self.parent.items.insert(0, self.parent.items.pop(index))
        else:
            self.parent.items.insert(index + 1, self.parent.items.pop(index))

    def check_integrity(self):
        assert isinstance(self.book, Book), self
        assert self in self.parent.items, self
        assert self.fullname in self.book.lookup, self
        assert os.path.exists(self.abspath), self


class Section(Item):
    "Directory containing other directories and Markdown text files"

    def __init__(self, book, parent, title):
        self.items = []
        super().__init__(book, parent, title)

    def __len__(self):
        "Number of characters in Markdown content in all texts in the sections."
        return sum([len(i) for i in self.all_texts])

    @property
    def is_section(self):
        return True

    def read(self):
        for itemtitle in sorted(os.listdir(self.abspath)):
            # Skip unsaved emacs files.
            if itemtitle.startswith(".#"):
                continue
            itempath = os.path.join(self.abspath, itemtitle)
            if os.path.isdir(itempath):
                self.items.append(Section(self.book, self, itemtitle))
            elif itemtitle.endswith(constants.MARKDOWN_EXT):
                self.items.append(Text(self.book, self, itemtitle))
            else:
                pass

    @property
    def all_items(self):
        "Return list of all sub-items. Self is not included."
        result = []
        for item in self.items:
            result.append(item)
            result.extend(item.all_items)
        return result

    @property
    def all_texts(self):
        "Return list of all sub-items that are texts."
        result = []
        for item in self.items:
            result.extend(item.all_texts)
        return result

    @property
    def n_words(self):
        "Approximate number of words in the texts of the section."
        return sum([i.n_words for i in self.all_texts])

    @property
    def status(self):
        "Return the lowest status for the sub-items."
        status = constants.FINAL
        for item in self.items:
            status = min(status, item.status)
        return status

    def filename(self, new=None):
        if new:
            return new
        else:
            return self.title

    def check_integrity(self):
        super().check_integrity()
        assert os.path.isdir(self.abspath), self


class Text(Item):
    "Markdown file."

    def __init__(self, book, parent, title):
        title, ext = os.path.splitext(title)
        assert not ext or ext == constants.MARKDOWN_EXT
        super().__init__(book, parent, title)

    def __len__(self):
        "Number of characters in Markdown content."
        return len(self.content)

    def __getitem__(self, key):
        return self.frontmatter[key]

    def __setitem__(self, key, value):
        self.frontmatter[key] = value

    @property
    def is_text(self):
        return True

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def read(self):
        "Read the frontmatter (if any) and content from the Markdown file."
        with open(self.abspath) as infile:
            content = infile.read()
        self.frontmatter, self.content = read_frontmatter(content)
        self.html = markdown.convert_to_html(self.content)
        self.ast = markdown.convert_to_ast(self.content)

    def write(self, content=None):
        """Write the text, with current frontmatter and the given Markdown content.
        If no Markdown content is provided, then use the current.
        Do some cleanup:
        - Strip each line from the right.
        - Do not write out multiple empty lines after another.
        """
        with open(self.abspath, "w") as outfile:
            write_frontmatter(outfile, self.frontmatter)
            if content is not None:
                lines = []
                prev_empty = False
                for line in content.split("\n"):
                    line = line.rstrip()
                    empty = not bool(line)
                    if empty and prev_empty:
                        continue
                    prev_empty = empty
                    lines.append(line)
                    lines.append("\n")
                self.content = "".join(lines)
            outfile.write(self.content)

    @property
    def all_items(self):
        "Return list of all sub-items. Self is *not* included."
        return []

    @property
    def all_texts(self):
        "Return list of all sub-items that are texts. Self *is* included."
        return [self]

    @property
    def n_words(self):
        return len(self.content.split())

    @property
    def status(self):
        return constants.Status.lookup(self.frontmatter.get("status"))

    @status.setter
    def status(self, status):
        if type(status) == str:
            status = constants.Status.lookup(status)
            if status is None:
                raise ValueError("Invalid status value.")
        elif not isinstance(status, constants.Status):
            raise ValueError("Invalid status instance.")
        self.frontmatter["status"] = repr(status)

    def filename(self, new=None):
        if new:
            return new + constants.MARKDOWN_EXT
        else:
            return self.title + constants.MARKDOWN_EXT

    def to_section(self):
        "Convert to section with the title of this text and move this text into it."
        oldtextpath = self.abspath
        sectionpath = os.path.splitext(oldtextpath)[0]
        os.mkdir(sectionpath)
        os.rename(oldtextpath, os.path.join(sectionpath, self.filename()))
        section = Section(self.book, self.parent, self.title)
        section.items[0] = self
        self.parent.items[self.index] = section
        self.book.lookup[section.fullname] = section
        self.parent = section
        self.book.lookup[self.fullname] = self
        self.book.frontmatter["items"] = self.book.get_items_order(self.book)
        self.book.index.write()
        return section

    def check_integrity(self):
        super().check_integrity()
        assert os.path.isfile(self.abspath)


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


if __name__ == "__main__":
    book = Book("/home/pekrau/Dropbox/texter/test")
    # book = Book("/home/pekrau/Dropbox/texter/lejonen")
    ic(book)
    ic(book.all_texts)
    # book.index.write()
    # book.archive()
