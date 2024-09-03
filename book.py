"Markdown book texts in files and directories."

from icecream import ic

import datetime
import os
import re
import shutil
import tarfile
import time
from urllib.parse import quote as urlquote

import yaml

import constants
import markdown

FRONTMATTER = re.compile(r"^---([\n\r].*?[\n\r])---[\n\r](.*)$", re.DOTALL)


class Book:
    "Root container for Markdown book texts in files and directories."

    def __init__(self, absdirpath):
        self.absdirpath = absdirpath
        self.title = os.path.basename(absdirpath)
        self.subtitle = None
        self.authors = []
        self.language = None
        self.read()

    def __str__(self):
        return self.title

    def __repr__(self):
        return f"Book('{self}')"

    def __len__(self):
        "Number of characters in Markdown content in all texts."
        return sum([len(i) for i in self.all_texts])

    def __getitem__(self, fullname):
        return self.lookup[fullname]

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
        return sum([i.n_words for i in self.all_texts])

    @property
    def status(self):
        "Return the lowest status for the sub-items."
        status = constants.STARTED
        for item in self.items:
            status = min(status, item.status)
        return status

    @property
    def is_text(self):
        return False

    def read(self):
        "Read all items from files. Set up references and indexed lookups."
        self.items = []

        # Section and Text instances for directories and files that actually exist.
        for itemname in sorted(os.listdir(self.absdirpath)):
            # Skip emacs temporary edit file.
            if itemname.startswith(".#"):
                continue

            itempath = os.path.join(self.absdirpath, itemname)
            if os.path.isdir(itempath):
                self.items.append(Section(self, self, itemname))
            elif itemname.endswith(constants.MARKDOWN_EXT):
                self.items.append(Text(self, self, itemname))
            else:
                pass

        self.lookup = {}
        for item in self.all_items:
            self.lookup[item.fullname] = item

        self.references = {}
        for item in self.all_texts:
            self.find_references(item, item.ast)

        self.indexed = {}
        for item in self.all_texts:
            self.find_indexed(item, item.ast)

    def find_references(self, item, ast):
        try:
            for child in ast["children"]:
                if isinstance(child, str): continue
                if child["element"] == "reference":
                    self.references.setdefault(child["reference"], set()).add(item)
                self.find_references(item, child)
        except KeyError:
            pass

    def find_indexed(self, item, ast):
        try:
            for child in ast["children"]:
                if isinstance(child, str): continue
                if child["element"] == "indexed":
                    self.indexed.setdefault(child["canonical"], set()).add(item)
                self.find_indexed(item, child)
        except KeyError:
            pass

    def get(self, fullname, default=None):
        return self.lookup.get(fullname, default)

    def get_settings(self):
        "Create the book entry for the settings file."
        return dict(title=self.title,
                    subtitle=self.subtitle,
                    authors=self.authors,
                    language=self.language,
                    items=[i.get_settings() for i in self.items])

    def apply_settings(self, settings):
        "Apply general settings; change the order of the items."
        self.title = settings["book"].get("title")
        self.subtitle = settings["book"].get("subtitle")
        self.authors = settings["book"].get("authors") or []
        self.language = settings["book"].get("language")
        original = dict([(i.title, i) for i in self.items])
        self.items = []
        for ordered in settings["book"].get("items", []):
            try:
                item = original.pop(ordered["title"])
            except KeyError:
                pass
            else:
                self.items.append(item)
                item.apply_settings(ordered)
        self.items.extend(original.values())

    def create_text(self, title, anchor=None):
        """Create a new empty text inside the anchor if it is a section,
        or after anchor if it is a text.
        Raise ValueError if there is a problem.
        """
        check_invalid_characters(title)
        if anchor is None:
            section = self
        elif anchor.is_text:
            section = anchor.parent
        else:
            section = anchor
        dirpath = os.path.join(section.abspath, title)
        filepath = dirpath + constants.MARKDOWN_EXT
        if os.path.exists(dirpath) or os.path.exists(filepath):
            raise ValueError(f"The title is already in use within '{section.fullname}'.")
        with open(filepath, "w") as outfile:
            pass
        new = Text(self, section, title)
        if anchor is None:
            section.items.append(new)
        elif anchor.is_text:
            section.items.insert(anchor.index + 1, new)
        else:
            section.items.append(new)
        self.lookup[new.fullname] = new
        return new

    def create_section(self, anchor, title):
        """Create a new empty section inside the anchor if it is a section,
        or after anchor if it is a text.
        Raise ValueError if there is a problem.
        """
        check_invalid_characters(title)
        if anchor.is_text:
            section = anchor.parent
        else:
            section = anchor
        dirpath = os.path.join(section.abspath, title)
        filepath = dirpath + constants.MARKDOWN_EXT
        if os.path.exists(dirpath) or os.path.exists(filepath):
            raise ValueError(f"The title is already in use within '{section.fullname}'.")
        os.mkdir(dirpath)
        new = Section(self, section, title)
        if anchor.is_text:
            section.items.insert(anchor.index + 1, new)
        else:
            section.items.append(new)
        self.lookup[new.fullname] = new
        return new

    def archive(self, books=None):
        """Write all files for texts to a gzipped tar file.
        Optionally include items from other books, using the name of each
        book as prefix; effectively a subdirectory.
        Return the archive filepath and the number of items written.
        Raise an OSError if any error.
        """
        filename = (
            time.strftime(constants.DATETIME_ISO_FORMAT, time.localtime()) + ".tgz"
        )
        archivefilepath = os.path.join(
            self.absdirpath, constants.ARCHIVE_DIRNAME, filename
        )
        with tarfile.open(archivefilepath, "x:gz") as archivefile:
            # By looping over top-level items, the special directories are avoided.
            for item in self.items:
                archivefile.add(item.abspath, arcname=item.filename(), recursive=True)

            if books:
                if not isinstance(books, list):
                    books = [books]
                for book in books:
                    archivefile.add(book.abspath, arcname=book.title, recursive=True)
        with tarfile.open(archivefilepath) as archivefile:
            result = len(archivefile.getnames())
        return archivefilepath, result

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
        return isinstance(self, Text)

    @property
    def is_section(self):
        return isinstance(self, Section)

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
        return ".".join([str(i) for i in self.ordinal]) + " " + self.title

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

    def read(self):
        "To be implemented by inheriting classes."
        raise NotImplementedError

    def get_settings(self):
        "To be implemented by inheriting classes."
        raise NotImplementedError

    def apply_settings(self, settings):
        "To be implemented by inheriting classes."
        raise NotImplementedError

    def retitle(self, newtitle):
        """Retitle the item.
        Raise ValueError if any problem.
        """
        if newtitle == self.title:
            return
        if not newtitle:
            raise ValueError("Empty string given for title.")
        check_invalid_characters(newtitle)
        newabspath = os.path.join(self.parent.abspath, self.filename(newtitle))
        if os.path.exists(newabspath):
            raise ValueError("The title is already in use.")
        oldfullnames = [self.fullname] + [i.fullname for i in self.all_items]
        oldabspath = self.abspath
        self.title = newtitle
        os.rename(oldabspath, self.abspath)
        self.replace_in_lookup(oldfullnames)

    def replace_in_lookup(self, oldfullnames):
        for oldfullname in oldfullnames:
            item = self.book.lookup.pop(oldfullname)
            self.book.lookup[item.fullname] = item

    def move_up(self):
        """Move this item one step towards the beginning of its list of sibling items.
        Raise ValueError if no movement was possible; already at the start of the list.
        """
        pos = self.parent.items.index(self)
        if pos == 0:
            raise ValueError("Item already at the start of the list.")
        self.parent.items.insert(pos - 1, self.parent.items.pop(pos))

    def move_down(self):
        """Move this item one step down towards the end of its list of sibling items.
        Raise ValueError if no movement was possible; already at the end of the list.
        """
        pos = self.parent.items.index(self)
        if pos == len(self.parent.items) - 1:
            raise ValueError("Item already at the end of the list.")
        self.parent.items.insert(pos + 1, self.parent.items.pop(pos))

    def move_to_parent(self):
        """Move this item one level up to the parent.
        It is placed after the old parent.
        Raise ValueError if any problem.
        """
        if self.parent == self.book:
            raise ValueError("Item is already at the top level.")
        newabspath = os.path.join(self.parent.parent.abspath, self.filename())
        if os.path.exists(newabspath):
            raise ValueError("Item cannot be moved up due to title collision.")
        oldabspath = self.abspath
        oldfullnames = [self.fullname] + [i.fullname for i in self.all_items]
        before = self.parent.next
        self.parent.items.remove(self)
        if before:
            self.parent.parent.items.insert(before.index, self)
        else:
            self.parent.parent.items.append(self)
        self.parent = self.parent.parent
        os.rename(oldabspath, self.abspath)
        self.replace_in_lookup(oldfullnames)

    def move_to_section(self, section):
        """Move this item one level down to the given section.
        It is placed last among the items of the section.
        Raise ValueError if any problem.
        """
        if not isinstance(section, Section):
            raise ValueError("Cannot move down into a non-section.")
        if section in self.all_items:
            raise ValueError("Cannot move down into a subsection of this section.")
        newabspath = os.path.join(section.abspath, self.filename())
        if os.path.exists(newabspath):
            raise ValueError("Item cannot be moved down due to title collision.")
        oldabspath = self.abspath
        oldfullnames = [self.fullname] + [i.fullname for i in self.all_items]
        self.parent.items.remove(self)
        section.items.append(self)
        self.parent = section
        os.rename(oldabspath, self.abspath)
        self.replace_in_lookup(oldfullnames)

    def copy(self, newtitle):
        "Common code for section and text copy operations."
        if newtitle == self.title:
            raise ValueError("Cannot copy to the same title.")
        if not newtitle:
            raise ValueError("Empty string given for title.")
        check_invalid_characters(newtitle)
        newabspath = os.path.join(self.parent.abspath, self.filename(newtitle))
        if os.path.exists(newabspath):
            raise ValueError("The title is already in use.")
        return newabspath

    def delete(self):
        "To be implemented by inheriting classes."
        raise NotImplementedError

    def check_integrity(self):
        assert isinstance(self.book, Book), self
        assert self in self.parent.items, self
        assert self.fullname in self.book.lookup, self
        assert os.path.exists(self.abspath), self


class Section(Item):
    "Directory."

    def __init__(self, book, parent, title):
        self.items = []
        super().__init__(book, parent, title)

    def __len__(self):
        "Number of characters in Markdown content in all texts in the sections."
        return sum([len(i) for i in self.all_texts])

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
        status = constants.STARTED
        for item in self.items:
            status = min(status, item.status)
        return status

    def filename(self, newtitle=None):
        if newtitle:
            return newtitle
        else:
            return self.title

    def read(self):
        for itemtitle in sorted(os.listdir(self.abspath)):
            itempath = os.path.join(self.abspath, itemtitle)
            if os.path.isdir(itempath):
                self.items.append(Section(self.book, self, itemtitle))
            elif itemtitle.endswith(constants.MARKDOWN_EXT):
                self.items.append(Text(self.book, self, itemtitle))
            else:
                pass

    def get_settings(self):
        "Create the entry for this section for the settings file."
        return dict(
            type="section",
            title=self.title,
            items=[i.get_settings() for i in self.items],
        )

    def apply_settings(self, settings):
        assert settings["type"] == "section"
        original = dict([(i.title, i) for i in self.items])
        self.items = []
        for ordered in settings["items"]:
            try:
                item = original.pop(ordered["title"])
            except KeyError:
                pass
            else:
                self.items.append(item)
                item.apply_settings(ordered)
        self.items.extend(original.values())

    def copy(self, newtitle):
        newabspath = super().copy(newtitle)
        shutil.copytree(self.abspath, newabspath)
        new = Section(self.book, self.parent, newtitle)
        self.parent.items.append(new)
        self.book.lookup[new.fullname] = new
        for item in new.all_items:
            self.book.lookup[item.fullname] = item
        return new

    def delete(self):
        shutil.rmtree(self.abspath)
        for item in self.all_items:
            self.book.lookup.pop(item.fullname)
        self.book.lookup.pop(self.fullname)
        self.parent.items.remove(self)
        self.book = None
        self.parent = None

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

    def __contains__(self, key):
        return key in self.frontmatter

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

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def pop(self, key, default=None):
        return self.frontmatter.pop(key, default)

    def get_status(self):
        return constants.Status.lookup(self.get("status"))

    def set_status(self, status):
        if type(status) == str:
            status = constants.Status.lookup(status)
            if status is None:
                raise ValueError("Invalid status value.")
        elif not isinstance(status, constants.Status):
            raise ValueError("Invalid status instance.")
        self.frontmatter["status"] = repr(status)

    status = property(get_status, set_status)

    def filename(self, newtitle=None):
        if newtitle:
            return newtitle + constants.MARKDOWN_EXT
        else:
            return self.title + constants.MARKDOWN_EXT

    def read(self):
        with open(self.abspath) as infile:
            self.content = infile.read()
        match = FRONTMATTER.match(self.content)
        if match:
            self.frontmatter = yaml.safe_load(match.group(1))
            self.content = self.content[match.start(2) :]
        else:
            self.frontmatter = {}
        self.html = markdown.convert_to_html(self.content)
        self.ast = markdown.convert_to_ast(self.content)

    def get_settings(self):
        "Create the entry for this text for the settings file."
        return dict(type="text", title=self.title, status=repr(self.status))

    def apply_settings(self, settings):
        assert settings["type"] == "text"

    def copy(self, newtitle):
        newabspath = super().copy(newtitle)
        shutil.copy2(self.abspath, newabspath)
        new = Text(self.book, self.parent, newtitle + constants.MARKDOWN_EXT)
        self.parent.items.append(new)
        self.book.lookup[new.fullname] = new
        return new

    def delete(self):
        os.remove(self.abspath)
        self.book.lookup.pop(self.fullname)
        self.parent.items.remove(self)
        self.book = None
        self.parent = None

    def write(self, content=None):
        """Write the text, with current frontmatter and the given Markdown content.
        If no Markdown content is provided, then use the current.
        Do some cleanup:
        - Strip each line from the right.
        - Do not write out multiple empty lines after another.
        """
        with open(self.abspath, "w") as outfile:
            if self.frontmatter:
                outfile.write("---\n")
                outfile.write(yaml.dump(self.frontmatter))
                outfile.write("---\n")
            if content is None:
                outfile.write(self.content or "")
            else:
                prev_empty = False
                for line in content.split("\n"):
                    line = line.rstrip()
                    empty = not bool(line)
                    if empty and prev_empty:
                        continue
                    prev_empty = empty
                    outfile.write(line)
                    outfile.write("\n")

    def check_integrity(self):
        super().check_integrity()
        assert os.path.isfile(self.abspath)


def check_invalid_characters(title):
    """Raise ValueError if title contains any invalid characters;
    those with special meaning in file system.
    """
    invalids = [os.extsep, os.sep]
    if os.altsep:
        invalids.append(os.altsep)
    for invalid in invalids:
        if invalid in title:
            raise ValueError(f"The title may not contain the character '{invalid}'.")


def test(keep=False):
    import tempfile

    content = "# Very basic Markdown.\n\n**Bold**.\n"
    dirpath = tempfile.mkdtemp()
    ic(dirpath)
    for filename in ["text1.md", "text2.md", "text3.md"]:
        with open(os.path.join(dirpath, filename), "w") as outfile:
            outfile.write(content)
    subdirpath = os.path.join(dirpath, "section1")
    os.mkdir(subdirpath)
    for filename in ["text1.md", "text2.md", "text3.md"]:
        with open(os.path.join(subdirpath, filename), "w") as outfile:
            outfile.write(content)

    book = Book(dirpath)
    book.check_integrity()
    section = book["section1"]
    section.copy("section2")
    book.check_integrity()
    section.retitle("subsection")
    book.check_integrity()
    section.move_to_section(book["section2"])
    book.check_integrity()
    book["section2"].delete()
    book.check_integrity()
    if not keep:
        shutil.rmtree(dirpath)


if __name__ == "__main__":
    book = Book("/home/pekrau/Dropbox/texter/lejonen")
    ic(book)
    ic(book.all_items)
