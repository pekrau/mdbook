"Markdown book texts in files and directories."

import copy
import datetime
import hashlib
from http import HTTPStatus as HTTP
import io
import os
import re
import shutil
import tarfile
import time

import yaml

import constants
import markdown
import utils
from utils import Error, Tx


# Book instances cache. Key: bid; value: Book instance.
_books = {}

# Cached references book.
_references = None


def read_books():
    # Read in all books into memory, including the references.
    global _books
    global _references
    _books.clear()
    for bid in os.listdir(os.environ["MDBOOK_DIR"]):
        dirpath = os.path.join(os.environ["MDBOOK_DIR"], bid)
        if not os.path.isdir(dirpath):
            continue
        if bid == constants.REFERENCES:
            continue
        try:
            book = Book(dirpath)
            _books[book.bid] = book
        except FileNotFoundError:
            pass
    dirpath = os.path.join(os.environ["MDBOOK_DIR"], constants.REFERENCES)
    if not os.path.exists(dirpath):
        os.mkdir(dirpath)
    _references = Book(dirpath)


def get_books():
    "Get the list of books, excluding references."
    return sorted(_books.values(), key=lambda b: b.modified, reverse=True)


def get_book(bid, refresh=False):
    "Get the book, optionally refreshing the cache."
    global _books
    if not bid:
        raise Error("no book identifier provided", HTTP.BAD_REQUEST)
    try:
        book = _books[bid]
        if refresh:
            book.read()
        return book
    except KeyError:
        raise Error(f"no such book '{bid}'", HTTP.NOT_FOUND)


def get_references(refresh=False):
    "Get the references book, optionally refreshing the cache."
    global _references
    if refresh:
        _references.read()
        _references.items.sort(key=lambda r: r["id"])
        _references.write()
    return _references


def get_state():
    "Return JSON for the overall state of this site."
    books = {}
    for book in get_books() + [get_references()]:
        books[book.bid] = dict(
            title=book.title,
            modified=utils.timestr(
                filepath=book.absfilepath, localtime=False, display=False
            ),
            sum_characters=book.frontmatter["sum_characters"],
            digest=book.frontmatter["digest"],
        )

    return dict(
        software=constants.SOFTWARE,
        version=constants.__version__,
        now=utils.timestr(localtime=False, display=False),
        type="site",
        books=books,
    )


FRONTMATTER = re.compile(r"^---([\n\r].*?[\n\r])---[\n\r](.*)$", re.DOTALL)


def read_markdown(target, filepath):
    "Read frontmatter and content from the Markdown file to the target."
    try:
        with open(filepath) as infile:
            content = infile.read()
    except FileNotFoundError:
        content = ""
    match = FRONTMATTER.match(content)
    if match:
        target.frontmatter = yaml.safe_load(match.group(1))
        target.content = content[match.start(2) :]
    else:
        target.frontmatter = {}
        target.content = content
    target.html = markdown.convert_to_html(target.content)
    target.ast = markdown.convert_to_ast(target.content)


def write_markdown(source, filepath):
    "Write frontmatter and content to the Markdown file from the source."
    with open(filepath, "w") as outfile:
        if source.frontmatter:
            outfile.write("---\n")
            outfile.write(yaml.dump(source.frontmatter, allow_unicode=True))
            outfile.write("---\n")
        if source.content:
            outfile.write(source.content)


def update_markdown(target, content):
    """If non-None content, then clean it:
    - Strip each line from the right. (Markdown line breaks not allowed.)
    - Do not write out multiple consecutive empty lines.
    Update members of the target, and return with True.
    Return True if any change, else False.
    """
    if content is None:
        return False
    lines = []
    prev_empty = False
    for line in content.split("\n"):
        line = line.rstrip()
        empty = not bool(line)
        if empty and prev_empty:
            continue
        prev_empty = empty
        lines.append(line)
    content = "\n".join(lines)
    changed = content != target.content
    if changed:
        target.content = content
        target.html = markdown.convert_to_html(target.content)
        target.ast = markdown.convert_to_ast(target.content)
    return changed


def get_copy_abspath(abspath):
    "Get the abspath for the next valid copy, and the number."
    abspath, ext = os.path.splitext(abspath)
    for number in [None] + list(range(2, constants.MAX_COPY_NUMBER + 1)):
        if number:
            newpath = f'{abspath}_{Tx("copy*")}_{number}{ext}'
        else:
            newpath = f'{abspath}_{Tx("copy*")}{ext}'
        if not os.path.exists(newpath):
            return newpath, number
    else:
        raise Error("could not form copy identifier; too many copies", HTTP.BAD_REQUEST)


class Book:
    "Root container for Markdown book texts in files and directories."

    def __init__(self, abspath):
        self.abspath = abspath
        self.read()

    def __str__(self):
        return self.title

    def __repr__(self):
        return f"Book('{self}')"

    def __getitem__(self, path):
        "Return the item (section or text) given its URL path."
        try:
            return self.path_lookup[path]
        except KeyError:
            raise Error(f"no such text '{path}'", HTTP.NOT_FOUND)

    def read(self):
        """ "Read the book from file.
        All items (sections, texts) recursively from files.
        Set up indexed and references lookups.
        """
        read_markdown(self, self.absfilepath)

        self.items = []

        # Section and Text instances for directories and files that actually exist.
        for name in sorted(os.listdir(self.abspath)):
            # Skip emacs temporary edit file.
            if name.startswith(".#"):
                continue
            # Do not include 'index.md' file; handled separately.
            if name == "index.md":
                continue

            if os.path.isdir(os.path.join(self.abspath, name)):
                # This will recursively read all items beneath this one.
                self.items.append(Section(self, self, name))

            elif name.endswith(constants.MARKDOWN_EXT):
                item = Text(self, self, os.path.splitext(name)[0])
                if not item.frontmatter.get("exclude"):
                    self.items.append(item)
            # Ignore other files.
            else:
                pass

        # Set the order to be that explicity given, if any.
        self.set_items_order(self, self.frontmatter.get("items", []))

        # Key: item path; value: item.
        self.path_lookup = {}
        for item in self.all_items:
            self.path_lookup[item.path] = item

        # Key: indexed term; value: set of texts.
        self.indexed = {}
        self.find_indexed(self, self.ast)
        # for item in self.all_texts:
        for item in self.all_items:
            self.find_indexed(item, item.ast)
            for keyword in item.get("keywords", []):
                self.indexed.setdefault(keyword, set()).add(item)

        # Key: reference identifier; value: set of texts.
        self.references = {}
        self.find_references(self, self.ast)
        # for item in self.all_texts:
        for item in self.all_items:
            self.find_references(item, item.ast)

        # Write out "index.md" if order changed.
        self.write()

    def write(self, content=None, force=False):
        """Write the 'index.md' file, if changed.
        If 'content' is not None, then update it.
        """
        changed = update_markdown(self, content)
        original = copy.deepcopy(self.frontmatter)
        self.frontmatter["items"] = self.get_items_order(self)
        self.frontmatter["type"] = self.type
        self.frontmatter["status"] = repr(self.status)
        self.frontmatter["sum_characters"] = self.sum_characters
        self.frontmatter["digest"] = self.digest
        if changed or force or (self.frontmatter != original):
            write_markdown(self, self.absfilepath)

    def set_items_order(self, container, items_order):
        "Chnage order of items in container according to given items_order."
        original = dict([i.name, i] for i in container.items)
        container.items = []
        for ordered in items_order:
            try:
                item = original.pop(ordered["name"])
            except KeyError:
                pass
            else:
                container.items.append(item)
                if isinstance(item, Section):
                    self.set_items_order(item, ordered.get("items", []))
        # Append items not already referenced in the frontmatter 'items'.
        container.items.extend(original.values())

    def get_items_order(self, container):
        "Return current order of items in this book."
        result = []
        for item in container.items:
            if item.is_text:
                result.append(dict(name=item.name, title=item.title))
            elif item.is_section:
                result.append(
                    dict(
                        name=item.name,
                        title=item.title,
                        items=self.get_items_order(item),
                    )
                )
        return result

    @property
    def bid(self):
        "The identifier of the book instance is not stored in its 'index.md'."
        return os.path.basename(self.abspath)

    @property
    def absfilepath(self):
        "Return the absolute file path of the 'index.md' file."
        return os.path.join(self.abspath, "index.md")

    @property
    def title(self):
        return self.frontmatter.get("title") or self.bid

    @title.setter
    def title(self, title):
        self.frontmatter["title"] = title

    @property
    def fulltitle(self):
        return Tx("Book")

    @property
    def path(self):
        "Required for the recursive call sequence from below."
        return ""

    @property
    def type(self):
        return "book" if len(self.frontmatter["items"]) else "article"

    @property
    def modified(self):
        return utils.timestr(filepath=self.absfilepath)

    @property
    def owner(self):
        return self.frontmatter.get("owner")

    @property
    def status(self):
        "Return the lowest status for the sub-items, or from 'index.md' if no items."
        if self.items:
            status = constants.FINAL
            for item in self.items:
                status = min(status, item.status)
        else:
            status = constants.Status.lookup(self.frontmatter.get("status"))
        return status

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
        "Approximate number of words in the 'index.md' of this book."
        return len(self.content.split())

    @property
    def sum_words(self):
        "Approximate number of words in the entire book."
        return sum([i.sum_words for i in self.items]) + len(self.content.split())

    @property
    def n_characters(self):
        "Approximate number of characters in the 'index.md' of this book."
        return len(self.content)

    @property
    def sum_characters(self):
        "Approximate number of characters in the entire book."
        return sum([i.sum_characters for i in self.items]) + len(self.content)

    @property
    def docx(self):
        return self.frontmatter.get("docx") or {}

    @property
    def pdf(self):
        return self.frontmatter.get("pdf") or {}

    @property
    def state(self):
        "Return a dictionary of the current state of the book."
        return dict(
            type="book",
            bid=self.bid,
            title=self.title,
            modified=utils.timestr(
                filepath=self.absfilepath, localtime=False, display=False
            ),
            n_characters=self.n_characters,
            sum_characters=self.sum_characters,
            digest=self.digest,
            items=[i.state for i in self.items],
        )

    @property
    def digest(self):
        """Return the hex digest of the contents of the book.
        Based on frontmatter (excluding digest!), content, and digests of items.
        """
        digest = utils.get_digest(self)
        for item in self.items:
            digest.update(item.digest.encode("utf-8"))
        return digest.hexdigest()

    @property
    def ordinal(self):
        return (0,)

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

    def find_references(self, item, ast):
        try:
            for child in ast["children"]:
                if isinstance(child, str):
                    continue
                if child["element"] == "reference":
                    self.references.setdefault(child["id"], set()).add(item)
                self.find_references(item, child)
        except KeyError:
            pass

    def get(self, path, default=None):
        "Return the item given its path."
        return self.path_lookup.get(path, default)

    def create_section(self, title, parent=None):
        """Create a new empty section inside the book or parent section.
        Raise ValueError if there is a problem.
        """
        assert parent is None or isinstance(parent, Section)
        if parent is None:
            parent = self
        name = utils.nameify(title)
        dirpath = os.path.join(parent.abspath, name)
        filepath = dirpath + constants.MARKDOWN_EXT
        if os.path.exists(dirpath) or os.path.exists(filepath):
            raise ValueError(f"The title '{title}' is already used within '{parent}'.")
        os.mkdir(dirpath)
        section = Section(self, parent, name)
        section.title = title
        parent.items.append(section)
        self.path_lookup[section.path] = section
        section.write()
        self.write()
        return section

    def create_text(self, title, parent=None):
        """Create a new empty text inside the book or parent section.
        Raise ValueError if there is a problem.
        """
        assert parent is None or isinstance(parent, Section)
        if parent is None:
            parent = self
        name = utils.nameify(title)
        dirpath = os.path.join(parent.abspath, name)
        filepath = dirpath + constants.MARKDOWN_EXT
        if os.path.exists(dirpath) or os.path.exists(filepath):
            raise ValueError(f"The title '{title}' is already used within '{parent}'.")
        text = Text(self, parent, name)
        text.title = title
        parent.items.append(text)
        self.path_lookup[text.path] = text
        text.write()
        self.write()
        return text

    def copy(self, owner=None):
        "Make a copy of the book."
        abspath, number = get_copy_abspath(self.abspath)
        try:
            shutil.copytree(self.abspath, abspath)
        except shutil.Error as error:
            raise Error(error, HTTP.CONFLICT)
        book = Book(abspath)
        if number:
            book.title = f'{self.title} ({Tx("copy*")} {number})'
        else:
            book.title = f'{self.title} ({Tx("copy*")})'
        if owner:
            book.frontmatter["owner"] = owner
        book.write()
        get_references(refresh=True)
        _books[book.bid] = book
        return book

    def delete(self, force=False):
        "Delete the book."
        global _books
        if not force and len(self.items) != 0:
            raise ValueError("Cannot delete non-empty book.")
        _books.pop(self.bid, None)
        shutil.rmtree(self.abspath)
        get_references(refresh=True)

    def get_tgzfile(self):
        """Write all files for the items in this book to a gzipped tar file.
        Return the BytesIO instance containing the tgz file.
        """
        result = io.BytesIO()
        with tarfile.open(fileobj=result, mode="w:gz") as tgzfile:
            tgzfile.add(self.absfilepath, arcname="index.md")
            for item in self.items:
                tgzfile.add(item.abspath, arcname=item.filename(), recursive=True)
        return result

    def search(self, term, ignorecase=True):
        "Find the set of items that contain the term in the content."
        if ignorecase:
            flags = re.IGNORECASE
        else:
            flags = 0
        result = set()
        if re.search(term, self.content, flags):
            result.add(self)
        for item in self.items:
            result.update(item.search(term, ignorecase=ignorecase))
        return result

    def check_integrity(self):
        assert os.path.exists(self.absfilepath)
        assert os.path.isfile(self.absfilepath)
        assert os.path.exists(self.abspath)
        assert os.path.isdir(self.abspath)
        assert len(self.path_lookup) == len(self.all_items)
        for item in self.all_items:
            assert item.book is self, (self, item)
            assert isinstance(item, Text) or isinstance(item, Section), (self, item)
            item.check_integrity()
        for text in self.all_texts:
            assert isinstance(text, Text), (self, text)


class Item:
    "Abstract class for sections and texts."

    def __init__(self, book, parent, name):
        self.book = book
        self.parent = parent
        self._name = name
        self.read()

    def __str__(self):
        return self.title

    def __repr__(self):
        return f"{self.__class__.__name__}('{self.path}')"

    def __getitem__(self, key):
        return self.frontmatter[key]

    def __setitem__(self, key, value):
        self.frontmatter[key] = value

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def set(self, key, value):
        "Set the item in the frontmatter, or delete it."
        if value:
            self.frontmatter[key] = value
        else:
            self.frontmatter.pop(key, None)

    def read(self):
        "To be implemented by inheriting classes. Recursive."
        raise NotImplementedError

    def write(self):
        "To be implemented by inheriting classes. *Not* recursive."
        raise NotImplementedError

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, name):
        """Set the name for the item.
        Changes the file or directory name of the item.
        Raise ValueError if any problem.
        """
        name = utils.nameify(name)
        if name == self.name:
            return
        if not name:
            raise ValueError("Empty string given for name.")
        newabspath = os.path.join(self.parent.abspath, self.filename(new=name))
        if name in self.parent.items or os.path.exists(newabspath):
            raise ValueError("The name is already in use.")
        if os.path.exists(newabspath):
            raise ValueError("The name is already in use.")
        items = [self] + self.all_items
        for item in items:
            self.book.path_lookup.pop(item.path)
        oldabspath = self.abspath
        self._name = name
        os.rename(oldabspath, newabspath)
        for item in items:
            self.book.path_lookup[item.path] = item
        self.book.write()

    @property
    def path(self):
        "The URL path to this item, without leading '/'. Concatenated names."
        if self.parent is self.book:
            return self.name
        else:
            return os.path.join(self.parent.path, self.name)

    @property
    def title(self):
        return self.frontmatter.get("title") or self.name

    @title.setter
    def title(self, title):
        self.frontmatter["title"] = title

    @property
    def fulltitle(self):
        "Concatenated title for this item."
        if self.parent is self.book:
            return self.title
        else:
            return f"{self.parent.fulltitle}; {self.title}"

    @property
    def level(self):
        result = 0
        parent = self.parent
        while parent is not None:
            result += 1
            parent = parent.parent
        return result

    @property
    def type(self):
        raise NotImplementedError

    @property
    def is_text(self):
        return self.type == "text"

    @property
    def is_section(self):
        return self.type == "section"

    @property
    def index(self):
        "The zero-based index of this item among its siblings."
        for count, item in enumerate(self.parent.items):
            if item is self:
                return count

    @property
    def digest(self):
        """Return the hex digest of the contents of the item.
        Based on frontmatter (excluding 'digest!') and content of the item.
        """
        return utils.get_digest(self).hexdigest()

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
    def prev_section(self):
        "Return the section sibling that closest backward to it, if any."
        index = self.index
        while index:
            item = self.parent.items[index - 1]
            if item.is_section:
                return item
            index -= 1
        return None

    @property
    def next(self):
        "Next sibling or None."
        try:
            return self.parent.items[self.index + 1]
        except IndexError:
            return None

    @property
    def chapter(self):
        "Top-level section or text for this item; possibly itself."
        item = self
        while item.parent is not self.book:
            item = item.parent
        return item

    @property
    def abspath(self):
        """The absolute path for this item.
        - Section: Directory path.
        - Text: File path.
        """
        return os.path.join(self.parent.abspath, self.filename())

    @property
    def absfilepath(self):
        """The absolute filepath ot this item.
        - Section: File path to 'index.md'.
        - Text: File path.
        To be implemented by inheriting classes.
        """
        raise NotImplementedError

    @property
    def language(self):
        return self.book.language

    def filename(self, newname=None):
        """Return the filename of this item.
        Note: this is not the path, just the base name of the file or directory.
        To be implemented by inheriting classes.
        """
        raise NotImplementedError

    def forward(self):
        "Move this item forward in its list of siblings. Loop around at end."
        index = self.index
        if index == len(self.parent.items) - 1:
            self.parent.items.insert(0, self.parent.items.pop(index))
        else:
            self.parent.items.insert(index + 1, self.parent.items.pop(index))
        # Write out book and refresh (references need not be refreshed).
        self.book.write()
        self.book.read()

    def backward(self):
        "Move this item backward in its list of siblings. Loop around at beginning."
        index = self.index
        if index == 0:
            self.parent.items.append(self.parent.items.pop(0))
        else:
            self.parent.items.insert(index - 1, self.parent.items.pop(index))
        # Write out book and refresh (references need not be refreshed).
        self.book.write()
        self.book.read()

    def outof(self):
        "Move this item out of its section into the section or book above."
        if self.parent is self.book:
            return
        old_abspath = self.abspath
        new_abspath = os.path.join(self.parent.parent.abspath, self.filename())
        # Must check both file and directory for name collision.
        for path in [
            new_abspath,
            os.path.splitext(new_abspath)[0],
            new_abspath + constants.MARKDOWN_EXT,
        ]:  # Doesn't matter if '.md.md'
            if os.path.exists(path):
                raise Error(
                    "cannot move item; name collision with an existing item",
                    HTTP.CONFLICT,
                )
        # Remove item and all its subitems from the path lookup of the book.
        self.book.path_lookup.pop(self.path)
        for item in self.all_items:
            self.book.path_lookup.pop(item.path)
        # Remove item from its parent's list of items.
        self.parent.items.remove(self)
        # Actually move the item on disk.
        os.rename(old_abspath, new_abspath)
        # Add item into the parent above, after the position of its old parent.
        pos = self.parent.parent.items.index(self.parent) + 1
        self.parent.parent.items.insert(pos, self)
        # Set the new parent for this item.
        self.parent = self.parent.parent
        # Add back this item and its subitems to the path lookup of the book.
        self.book.path_lookup[self.path] = self
        for item in self.all_items:
            self.book.path_lookup[item.path] = item
        self.check_integrity()
        # Write out book and refresh everything.
        self.book.write()
        self.book.read()
        get_references(refresh=True)

    def into(self):
        "Move this item into the section closest backward of it."
        section = self.prev_section
        if not section:
            return
        old_abspath = self.abspath
        new_abspath = os.path.join(section.abspath, self.filename())
        # Must check both file and directory for name collision.
        for path in [
            new_abspath,
            os.path.splitext(new_abspath)[0],
            new_abspath + constants.MARKDOWN_EXT,
        ]:  # Doesn't matter if '.md.md'
            if os.path.exists(path):
                raise Error(
                    "cannot move item; name collision with an existing item",
                    HTTP.CONFLICT,
                )
        # Remove item and all its subitems from the path lookup of the book.
        self.book.path_lookup.pop(self.path)
        for item in self.all_items:
            self.book.path_lookup.pop(item.path)
        # Remove item from its parent's list of items.
        self.parent.items.remove(self)
        # Actually move the item on disk.
        os.rename(old_abspath, new_abspath)
        # Add item into the section, as the last one.
        section.items.append(self)
        # Set the new parent for this item.
        self.parent = section
        # Add back this item and its subitems to the path lookup of the book.
        self.book.path_lookup[self.path] = self
        for item in self.all_items:
            self.book.path_lookup[item.path] = item
        self.check_integrity()
        # Write out book and refresh everything.
        self.book.write()
        self.book.read()
        get_references(refresh=True)

    def copy(self):
        "Copy this item."
        raise NotImplementedError

    def delete(self):
        "Delete this item from the book."
        raise NotImplementedError

    def search(self, term, ignorecase=True):
        "Find the set of items that contain the term in the content."
        raise NotImplementedError

    def check_integrity(self):
        assert isinstance(self.book, Book)
        assert self in self.parent.items
        assert self.path in self.book.path_lookup
        assert os.path.exists(self.abspath)


class Section(Item):
    "Directory containing other directories and Markdown text files"

    def __init__(self, book, parent, name):
        self.items = []
        super().__init__(book, parent, name)

    def read(self):
        """Read all items in the subdirectory, and the 'index.md' file, if any.
        This is recursive; all sections and texts below this are also read.
        """
        read_markdown(self, self.absfilepath)
        for name in sorted(os.listdir(self.abspath)):
            # Skip temporary emacs files.
            if name.startswith(".#"):
                continue
            # Skip the already read 'index.md' file.
            if name == "index.md":
                continue
            if os.path.isdir(os.path.join(self.abspath, name)):
                self.items.append(Section(self.book, self, name))
            elif name.endswith(constants.MARKDOWN_EXT):
                self.items.append(Text(self.book, self, os.path.splitext(name)[0]))
            else:  # Skip any non-Markdown files.
                pass
        # Repair if no 'index.md' in the directory.
        if not os.path.exists(self.absfilepath):
            write_markdown(self, self.absfilepath)

    def write(self, content=None, force=False):
        """Write the 'index.md' file, if changed.
        If 'content' is not None, then update it.
        This is *not* recursive.
        """
        changed = update_markdown(self, content)
        original = copy.deepcopy(self.frontmatter)
        self.frontmatter["digest"] = self.digest
        if changed or force or (self.frontmatter != original):
            write_markdown(self, self.absfilepath)

    @property
    def type(self):
        return "section"

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
        "Approximate number of words in 'index.md' of this section."
        return len(self.content.split())

    @property
    def sum_words(self):
        "Approximate number of words in the entire section."
        return sum([i.sum_words for i in self.items]) + len(self.content.split())

    @property
    def n_characters(self):
        "Approximate number of characters in the 'index.md' of this section."
        return len(self.content)

    @property
    def sum_characters(self):
        "Approximate number of characters in the entire section."
        return sum([i.sum_characters for i in self.items]) + len(self.content)

    @property
    def modified(self):
        return utils.timestr(filepath=self.absfilepath)

    @property
    def status(self):
        "Return the lowest status for the sub-items."
        if self.items:
            status = constants.FINAL
            for item in self.items:
                status = min(status, item.status)
        else:
            status = constants.STATUSES[0]
        return status

    @property
    def state(self):
        "Return a dictionary of the current state of the section."
        return dict(
            type="section",
            name=self.name,
            title=self.title,
            modified=utils.timestr(
                filepath=self.absfilepath, localtime=False, display=False
            ),
            n_characters=self.n_characters,
            digest=self.digest,
            items=[i.state for i in self.items],
        )

    @property
    def absfilepath(self):
        "The absolute filepath of the 'index.md' for this section."
        return os.path.join(self.abspath, "index.md")

    def filename(self, new=None):
        """Return the filename of this section.
        Note: this is not the path, just the base name of the directory.
        """
        if new:
            return utils.nameify(new)
        else:
            return self.name

    def copy(self):
        "Make a copy of this section and all below it."
        abspath, number = get_copy_abspath(self.abspath)
        try:
            shutil.copytree(self.abspath, abspath)
        except shutil.Error as error:
            raise Error(error, HTTP.CONFLICT)
        section = Section(self.book, self.parent, os.path.basename(abspath))
        if number:
            section.frontmatter["title"] = f'{self.title} ({Tx("copy*")} {number})'
        else:
            section.frontmatter["title"] = f'{self.title} ({Tx("copy*")})'
        self.parent.items.insert(self.index + 1, section)
        section.write()
        path = section.path
        self.book.write()
        self.book.read()
        get_references(refresh=True)
        return path

    def delete(self, force=False):
        "Delete this section from the book."
        if not force and len(self.items) != 0:
            raise ValueError("Cannot delete non-empty section.")
        self.book.path_lookup.pop(self.path)
        self.parent.items.remove(self)
        shutil.rmtree(self.abspath)
        self.book.write()
        get_references(refresh=True)

    def search(self, term, ignorecase=True):
        "Find the set of items that contain the term in the content."
        if ignorecase:
            flags = re.IGNORECASE
        else:
            flags = 0
        result = set()
        if re.search(term, self.content, flags):
            result.add(self)
        for item in self.items:
            result.update(item.search(term, ignorecase=ignorecase))
        return result

    def check_integrity(self):
        super().check_integrity()
        assert os.path.isdir(self.abspath)


class Text(Item):
    "Markdown file."

    def read(self):
        "Read the frontmatter (if any) and content from the Markdown file."
        read_markdown(self, self.abspath)

    def write(self, content=None, force=False):
        """Write the text, if changed.
        If 'content' is not None, then update it.
        """
        changed = update_markdown(self, content)
        original = copy.deepcopy(self.frontmatter)
        self.frontmatter["digest"] = self.digest
        if changed or force or (self.frontmatter != original):
            write_markdown(self, self.abspath)

    @property
    def type(self):
        return "text"

    @property
    def items(self):
        "Return list of sub-items. Self is *not* included."
        return []

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
        "Approximate number of words in the text."
        return len(self.content.split())

    @property
    def sum_words(self):
        "Approximate number of words in the text."
        return self.n_words

    @property
    def n_characters(self):
        "Approximate number of characters in the text."
        return len(self.content)

    @property
    def sum_characters(self):
        "Approximate number of characters in the text."
        return self.n_characters

    @property
    def modified(self):
        return utils.timestr(filepath=self.abspath)

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

    @property
    def state(self):
        "Return a dictionary of the current state of the text."
        return dict(
            type="text",
            name=self.name,
            title=self.title,
            modified=utils.timestr(
                filepath=self.abspath, localtime=False, display=False
            ),
            n_characters=self.n_characters,
            digest=self.digest,
        )

    @property
    def absfilepath(self):
        "The absolute filepath ot this text."
        return self.abspath

    def filename(self, new=None):
        """Return the filename of this text; optionally if the new title were set.
        Note: this is not the path, just the base name of the file.
        """
        if new:
            return utils.nameify(new) + constants.MARKDOWN_EXT
        else:
            return self.name + constants.MARKDOWN_EXT

    def to_section(self):
        "Create a section with the title of this text and move this text into it."
        oldtextpath = self.abspath
        sectionpath = os.path.splitext(oldtextpath)[0]
        os.mkdir(sectionpath)
        os.rename(oldtextpath, os.path.join(sectionpath, self.filename()))
        section = Section(self.book, self.parent, self.name)
        section.title = self.title
        section.items[0] = self
        self.parent.items[self.index] = section
        section.write()
        self.book.read()
        return section

    def copy(self):
        "Make a copy of this text."
        from icecream import ic

        abspath, number = get_copy_abspath(self.abspath)
        ic(self.abspath, abspath)
        try:
            shutil.copy2(self.abspath, abspath)
        except shutil.Error as error:
            raise Error(error, HTTP.CONFLICT)

        text = Text(
            self.book, self.parent, os.path.splitext(os.path.basename(abspath))[0]
        )
        if number:
            text.frontmatter["title"] = f'{self.title} ({Tx("copy*")} {number})'
        else:
            text.frontmatter["title"] = f'{self.title} ({Tx("copy*")})'
        self.parent.items.insert(self.index + 1, text)
        text.write()
        path = text.path
        self.book.write()
        self.book.read()
        get_references(refresh=True)
        return path

    def delete(self, force=False):
        "Delete this text from the book."
        self.book.path_lookup.pop(self.path)
        self.parent.items.remove(self)
        os.remove(self.abspath)
        self.book.write()

    def search(self, term, ignorecase=True):
        "Find the set of items that contain the term in the content."
        if ignorecase:
            flags = re.IGNORECASE
        else:
            flags = 0
        if re.search(term, self.content, flags):
            return set([self])
        else:
            return set()

    def check_integrity(self):
        super().check_integrity()
        assert os.path.isfile(self.abspath)


if __name__ == "__main__":
    timer = utils.Timer()
    book = Book("/home/pekrau/Dropbox/mdbooks/lejonen")
    print(timer)
    timer.restart()
    book.check_integrity()
    print(timer)
    timer.restart()
    result = book.search("XXX")
    print(timer)
    timer.restart()
    result = book.search("XXX", ignorecase=False)
    print(timer)
    print(result)
    print(book, book.sum_words, book.sum_characters)
