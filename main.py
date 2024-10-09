"Web view and edit of Markdown book contents."

from icecream import ic

import copy
import io
import os
import string
import sys
import tarfile
import urllib

from fasthtml.common import *
import bibtexparser
import yaml

import constants
import docx_creator
import pdf_creator
import utils

from book import Book, read_frontmatter, write_frontmatter, check_disallowed_characters

NAV_STYLE_TEMPLATE = "outline-color: {color}; outline-width:8px; outline-style:solid; padding:0px 10px; border-radius:5px;"

Tx = utils.Tx

app, rt = fast_app(live=True, static_path="static")

try:
    MDBOOK_DIR = os.environ["MDBOOK_DIR"]
except KeyError:
    if len(sys.argv) == 2:
        MDBOOK_DIR = sys.argv[1]
    else:
        MDBOOK_DIR = os.getcwd()

# Book instances cache. Key: bid; value: Book instance.
books = {}


def get_book(bid):
    "Get the book contents, cached."
    global books
    try:
        return books[bid]
    except KeyError:
        book = Book(os.path.join(MDBOOK_DIR, bid))
        books[bid] = book
        return book


def get_references():
    "Get the references book, cached."
    global _references
    try:
        return_references
    except NameError:
        _references = Book(os.path.join(MDBOOK_DIR, constants.REFERENCES_DIR))
        return _references


def error(message):
    return Response(status_code=409, content=message)


def metadata(item):
    n_words = f"{utils.thousands(item.n_words)}"
    n_characters = f"{utils.thousands(len(item))}"
    items = [Tx(item.status),
             f'{n_words} {Tx("words")}; {n_characters} {Tx("characters")}']
    if isinstance(item, Book) and item.frontmatter.get("language"):
        items.append(item.frontmatter["language"])
    return "; ".join(items)


def nav(book=None, item=None, title=None, actions=None):
    "The standard navigation bar."
    if book is None:
        entries = [Ul(Li(A(Img(src="/mdbook.svg"), href="/")))]
    else:
        entries = [
            Ul(
                Li(A(Img(src="/mdbook.svg"), href="/")),
                Li(A(book.title, href=f"/{book.id}")),
            )
        ]
    if item is not None:
        entries.append(
            Ul(
                Li(
                    Strong(item.fullname),
                    Br(),
                    Small(metadata(item)),
                )
            )
        )
        nav_style = NAV_STYLE_TEMPLATE.format(color=item.status.color)
    elif book is not None:
        entries.append(
            Ul(
                Li(
                    Small(metadata(book)),
                )
            )
        )
        nav_style = NAV_STYLE_TEMPLATE.format(color=book.status.color)
    elif title:
        entries.append(Ul(Li(Strong(title))))
        if book is None:
            nav_style = NAV_STYLE_TEMPLATE.format(color="black")
        else:
            nav_style = NAV_STYLE_TEMPLATE.format(color=book.status.color)
    elif book is not None:
        entries.append(Ul(Li(f"Status: {Tx(book.status)}")))
        nav_style = NAV_STYLE_TEMPLATE.format(color=book.status.color)
    else:
        nav_style = NAV_STYLE_TEMPLATE.format(color="black")
    pages = []
    if item is not None:
        if item.parent:
            if item.parent.level == 0:  # Book.
                url = "/"
            elif item.parent.is_section:
                url = f"/{book.id}/section/{item.parent.urlpath}"
            else:
                url = f"/{book.id}/text/{item.parent.urlpath}"
            pages.append(A(NotStr(f"&ShortUpArrow; {item.parent.title}"), href=url))
        if item.prev:
            if item.prev.is_section:
                url = f"/{book.id}/section/{item.prev.urlpath}"
            else:
                url = f"/{book.id}/text/{item.prev.urlpath}"
            pages.append(A(NotStr(f"&ShortLeftArrow; {item.prev.title}"), href=url))
        if item.next:
            if item.next.is_section:
                url = f"/{book.id}/section/{item.next.urlpath}"
            else:
                url = f"/{book.id}/text/{item.next.urlpath}"
            pages.append(A(NotStr(f"&ShortRightArrow; {item.next.title}"), href=url))
    if book is not None:
        pages.extend(
            [
                A(Tx("Title"), href=f"/{book.id}/title"),
                A(Tx("Index"), href=f"/{book.id}/index"),
                A(Tx("Statuslist"), href=f"/{book.id}/statuslist"),
            ]
        )
    pages.append(A(Tx("References"), href="/references"))
    items = []
    if len(pages) == 1:
        if title != Tx("References"):
            items.append(Ul(Li(pages[0], NotStr("&nbsp;"))))
    else:
        items.append(
            Li(
                Details(
                    Summary(Tx("Pages")), Ul(*[Li(p) for p in pages]), cls="dropdown"
                )
            )
        )
    if actions:
        items.append(
            Li(
                Details(
                    Summary(Tx("Actions")),
                    Ul(*[Li(c) for c in actions]),
                    cls="dropdown",
                )
            )
        )
    if items:
        entries.append(Ul(*items))
    return Nav(*entries, style=nav_style)


def toc(book, items, show_arrows=False):
    "Recursive lists of sections and texts."
    parts = []
    for item in items:
        if show_arrows:
            arrows = [
                NotStr("&nbsp;"),
                A(NotStr("&ShortUpArrow;"), href=f"/{book.id}/up/{item.urlpath}"),
                NotStr("&nbsp;"),
                A(NotStr("&ShortDownArrow;"), href=f"/{book.id}/down/{item.urlpath}"),
            ]
        else:
            arrows = []
        if item.is_section:
            parts.append(
                Li(
                    A(
                        str(item),
                        style=f"color: {item.status.color};",
                        href=f"/{book.id}/section/{item.urlpath}",
                    ),
                    NotStr("&nbsp;&nbsp;&nbsp;"),
                    Small(metadata(item), style="color: silver;"),
                    *arrows,
                    style=f"color: {item.status.color};",
                )
            )
            parts.append(toc(book, item.items, show_arrows=show_arrows))
        elif item.is_text:
            if item.frontmatter.get("suppress_title"):
                title = Del(str(item))
            else:
                title = str(item)
            parts.append(
                Li(
                    A(
                        title,
                        style=f"color: {item.status.color};",
                        href=f"/{book.id}/text/{item.urlpath}",
                    ),
                    NotStr("&nbsp;&nbsp;&nbsp;"),
                    Small(metadata(item)),
                    *arrows,
                )
            )
    return Ol(*parts)


@rt("/")
def get():
    "Home page; list of books."
    books = []
    for bid in os.listdir(MDBOOK_DIR):
        if bid == constants.REFERENCES_DIR:
            continue
        try:
            dirpath = os.path.join(MDBOOK_DIR, bid)
            filepath = os.path.join(dirpath, "index.md")
            with open(filepath) as infile:
                frontmatter, content = read_frontmatter(infile.read())
            books.append(
                {
                    "bid": bid,
                    "title": frontmatter.get("title", bid),
                    "dirpath": dirpath,
                    "authors": frontmatter.get("authors", []),
                    "modified": utils.timestr(filepath),
                }
            )
        except OSError:
            pass
    books.sort(key=lambda b: b["modified"], reverse=True)
    rows = []
    for book in books:
        rows.append(
            Tr(Td(A(book["title"], href=f'/{book["bid"]}')), Td(book["modified"]))
        )
    return (
        Title("mdbooks"),
        Header(
            nav(
                title="mdbooks",
                actions=[
                    A(f'{Tx("Create")} {Tx("book")}', href="/book"),
                    A(f'{Tx("Download")} TGZ', href="/tgz"),
               ],
            ),
            cls="container",
        ),
        Main(Table(*rows), cls="container"),
    )


@rt("/tgz")
def get():
    "Download a gzipped tar file of all books."
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as archivefile:
        for name in os.listdir(MDBOOK_DIR):
            archivefile.add(os.path.join(MDBOOK_DIR, name), arcname=name, recursive=True)
    filename = f"mdbooks {utils.timestr()}.tgz"
    return Response(
        content=output.getvalue(),
        media_type=constants.GZIP_MIMETYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@rt("/references")
def get():
    "Page for list of references."
    references = get_references()
    references.read()
    items = []
    for ref in references.items:
        parts = [
            Img(
                src="/clipboard.svg",
                title="Refid to clipboard",
                style="cursor: pointer;",
                cls="to_clipboard",
                data_clipboard_text=f'[@{ref["id"]}]',
            ),
            NotStr("&nbsp;"),
            A(
                Strong(ref["id"], style="color: royalblue;"),
                href=f'/reference/{ref["id"].replace(" ", "_")}',
            ),
            NotStr("&nbsp;"),
        ]
        if ref.get("authors"):
            authors = [utils.short_name(a) for a in ref["authors"]]
            if len(authors) > 4:
                authors = authors[:4] + ["..."]
            parts.append(", ".join(authors))
        if ref.get("year"):
            parts.append(f'({ref["year"]})')
        if ref.get("edition_published"):
            parts.append(f'[{ref["edition_published"]}]')
        if ref.get("title"):
            parts.append(Br())
            parts.append(ref["title"])

        links = []
        if ref.get("type") == "article":
            parts.append(Br())
            parts.append(I(ref["journal"]))
            if ref.get("volume"):
                parts.append(ref["volume"])
            if ref.get("number"):
                parts.append(f'({ref["number"]})')
            if ref.get("pages"):
                parts.append(":")
                parts.append(f'pp. {ref["pages"].replace("--", "-")}.')
        elif ref.get("type") == "book":
            parts.append(Br())
            if ref.get("publisher"):
                parts.append(f'{ref["publisher"]}.')
            if ref.get("isbn"):
                symbol, url = constants.REFERENCE_LINKS["isbn"]
                url = url.format(value=ref["isbn"])
                if links:
                    links.append(", ")
                links.append(
                    A(f'{symbol}:{ref["isbn"]}', href=url.format(value=ref["isbn"]))
                )

        if ref.get("url"):
            parts.append(Br())
            parts.append(A(ref["url"], href=ref["url"]))
            if ref.get("accessed"):
                parts.append(f'(Accessed: {ref["accessed"]})')
        if ref.get("doi"):
            symbol, url = constants.REFERENCE_LINKS["doi"]
            url = url.format(value=ref["doi"])
            if links:
                links.append(", ")
            links.append(A(f'{symbol}:{ref["doi"]}', href=url.format(value=ref["doi"])))
        if ref.get("pmid"):
            symbol, url = constants.REFERENCE_LINKS["pmid"]
            url = url.format(value=ref["pmid"])
            if links:
                links.append(", ")
            links.append(
                A(f'{symbol}:{ref["pmid"]}', href=url.format(value=ref["pmid"]))
            )

        if links:
            parts.append(" ")
            parts.extend(links)

        # XXX link to book text using the reference
        # xrefs = []
        # texts = get_book().references.get(ref["id"], [])
        # for text in sorted(texts, key=lambda t: t.ordinal):
        #     if xrefs:
        #         xrefs.append(Br())
        #     xrefs.append(A(text.fullname,
        #                    cls="secondary",
        #                    href=f"/text/{text.fullname}"))
        # if xrefs:
        #     parts.append(Small(Br(), *xrefs))
        items.append(P(*parts, id=ref["id"].replace(" ", "_")))

    return (
        Title(Tx("References")),
        Header(
            nav(title=Tx("References"), actions=[A(Tx("Add BibTex"), href="/bibtex")]),
            cls="container",
        ),
        Main(*items, cls="container"),
    )


@rt("/reference/{refid:str}")
def get(refid: str):
    "Page for details of a reference."
    ref = get_references()[refid.replace("_", " ")]
    rows = [
        Tr(
            Td(Tx("Identifier")),
            Td(
                f'{ref["id"]}',
                NotStr("&nbsp;"),
                Img(
                    src="/clipboard.svg",
                    title="Refid to clipboard",
                    style="cursor: pointer;",
                    cls="to_clipboard",
                    data_clipboard_text=f'[@{ref["id"]}]',
                ),
            ),
        ),
        Tr(Td(Tx("Authors")), Td("; ".join(ref.get("authors") or []))),
    ]
    for key in [
        "year",
        "title",
        "subtitle",
        "type",
        "edition_published",
        "language",
        "date",
        "keywords",
        "journal",
        "volume",
        "number",
        "pages",
        "publisher",
        "source",
    ]:
        value = ref.get(key)
        if value:
            rows.append(Tr(Td((Tx(key.replace("_", " ")).title())), Td(value)))
    if ref.get("issn"):
        rows.append(Tr(Td("ISSN"), Td(ref["issn"])))
    if ref.get("isbn"):
        url = constants.REFERENCE_LINKS["isbn"][1].format(value=ref["isbn"])
        rows.append(Tr(Td("ISBN"), Td(A(ref["isbn"], href=url))))
    if ref.get("pmid"):
        url = constants.REFERENCE_LINKS["pmid"][1].format(value=ref["pmid"])
        rows.append(Tr(Td("PubMed"), Td(A(ref["pmid"], href=url))))
    if ref.get("doi"):
        url = constants.REFERENCE_LINKS["doi"][1].format(value=ref["doi"])
        rows.append(Tr(Td("DOI"), Td(A(ref["doi"], href=url))))
    if ref.get("url"):
        rows.append(Tr(Td("Url"), Td(A(ref["url"], href=ref["url"]))))
    return (
        Title(refid),
        Script(src="/clipboard.min.js"),
        Script("new ClipboardJS('.to_clipboard');"),
        Header(
            nav(
                title=ref["id"],
                actions=[
                    A(
                        Tx("Clipboard"),
                        href="#",
                        cls="to_clipboard",
                        data_clipboard_text=f'[@{ref["id"]}]',
                    ),
                ],
            ),
            cls="container",
        ),
        Main(Table(*rows), Div(NotStr(ref.html)), cls="container"),
    )


@rt("/bibtex")
def get():
    "Page for adding reference(s) using BibTex data."
    return (
        Title("Add reference"),
        Header(nav(title="Add reference"), cls="container"),
        Main(
            Form(
                Fieldset(Legend(Tx("Bibtex data")), Textarea(name="data", rows="20")),
                Button("Add"),
                action="/bibtex",
                method="post",
            ),
            cls="container",
        ),
    )


@rt("/bibtex")
def post(data:str):
    "Actually add reference(s) using BibTex data."
    result = []
    for entry in bibtexparser.parse_string(data).entries:
        authors = utils.cleanup(entry.fields_dict["author"].value)
        authors = [a.strip() for a in authors.split(" and ")]
        year = entry.fields_dict["year"].value.strip()
        name = authors[0].split(",")[0].strip()
        for char in [""] + list("abcdefghijklmnopqrstuvxyz"):
            id = f"{name} {year}{char}"
            if get_references().get(id) is None:
                break
        else:
            raise ValueError(f"Could not form unique id for {name} {year}.")
        new = dict(id=id, type=entry.entry_type, authors=authors, year=year)
        for key, field in entry.fields_dict.items():
            if key == "author":
                continue
            value = utils.cleanup(field.value).strip()
            if value:
                new[key] = value
        # Split keywords into a list.
        try:
            new["keywords"] = [k.strip() for k in new["keywords"].split(";")]
        except KeyError:
            pass
        # Change month into date; sometimes has day number.
        try:
            month = new.pop("month")
        except KeyError:
            pass
        else:
            parts = month.split("#")
            if len(parts) == 2:
                month = constants.MONTHS[parts[1].strip().lower()]
                day = int("".join([c for c in parts[0] if c in string.digits]))
            else:
                month = constants.MONTHS[parts[0].strip().lower()]
                day = 0
            new["date"] = f"{year}-{month:02d}-{day:02d}"
        # Change page numbers double dash to single dash.
        try:
            pages = new.pop("pages")
        except KeyError:
            pass
        else:
            new["pages"] = pages.replace("--", "-")
        abstract = new.pop("abstract", None)
        reference = get_references().create_text(new["id"])
        for key, value in new.items():
            reference[key] = value
        if abstract:
            reference.write("**Abstract**\n\n" + abstract)
        else:
            reference.write()
        references = get_references()
        references.read()
        references.items.sort(key=lambda r: r["id"].lower())
        references.write_index()
        result.append(reference)
    return (
        Title("Added reference(s)"),
        Header(nav(title="Added reference(s)"), cls="container"),
        Main(
            Ul(*[Li(A(r["id"], href=f'/reference/{r["id"]}')) for r in result]),
            cls="container",
        ),
    )


@rt("/book")
def get():
    "Page to create and/or upload book using a gzipped tar file."
    title = f'{Tx("Create or upload")} {Tx("book")}'
    return (
        Title(title),
        Header(nav(title=title), cls="container"),
        Main(
            Form(
                Fieldset(
                    Legend(Tx("Title")),
                    Input(type="text", name="bid", required=True, autofocus=True),
                ),
                Fieldset(
                    Legend(Tx(f'{Tx("Upload")} TGZ')),
                    Input(type="file", name="tgzfile")
                ),
                Button(Tx("Create or upload")),
                action="/book",
                method="post",
            ),
            cls="container",
        ),
    )


@rt("/book")
async def post(bid:str, tgzfile:UploadFile=None):
    "Actually create and/or upload book using a gzipped tar file."
    if not bid:
        return error("No book identifier provided.")
    try:
        check_disallowed_characters(bid)
    except ValueError:
        return error(f'Book identifier "{bid}" contains disallowed characters.')
    dirpath = os.path.join(MDBOOK_DIR, bid)
    try:
        os.mkdir(dirpath)
    except FileExistsError:
        return error(f'Book "{bid}" already exists.')
    content = await tgzfile.read()
    if content:
        try:
            tf = tarfile.open(fileobj=io.BytesIO(content), mode="r:gz")
            if "index.md" not in tf.getnames():
                raise ValueError("No 'index.md' file in TGZ file; not from mdbook?")
            tf.extractall(path=dirpath)
        except (tarfile.TarError, ValueError) as msg:
            return error(f"Error reading TGZ file: {msg}")
        # XXX change owner of book
    else:
        with open(os.path.join(dirpath, "index.md"), "w") as outfile:
            write_frontmatter(outfile,
                              {"owner": "XXX", "status": repr(constants.STARTED)})
    return Redirect(f"/{bid}")


@rt("/{bid}")
def get(bid: str):
    "Book home page; list of sections and texts."
    book = get_book(bid)
    book.read()
    actions = [
        A(f'{Tx("Edit")}', href=f"/{bid}/edit"),
        A(f'{Tx("Status list")}', href=f"/{bid}/statuslist"),
        A(f'{Tx("Create")} {Tx("section")}', href=f"/{bid}/create_section"),
        A(f'{Tx("Create")} {Tx("text")}', href=f"/{bid}/create_text"),
        A(f'{Tx("Download")} DOCX', href=f"/{bid}/docx"),
        A(f'{Tx("Download")} PDF', href=f"/{bid}/pdf"),
        A(f'{Tx("Download")} TGZ', href=f"/{bid}/tgz"),
    ]
    if len(book.items) == 0:
        actions.append(A(f'{Tx("Delete")}', href=f"/{bid}/delete/"))
    return (
        Title(book.title),
        Header(nav(book=book, actions=actions), cls="container"),
        Main(toc(book, book.items, show_arrows=True), cls="container"),
    )


@rt("/{bid}/edit")
def get(bid:str):
    "Page for editing the book data."
    book = get_book(bid)
    fields = [
        Fieldset(
            Label(Tx("Title")),
            Input(name="title", value=book.frontmatter.get("title", ""),
                  autofocus=True),
        ),
        Fieldset(
            Label(Tx("Subtitle")),
            Input(name="subtitle", value=book.frontmatter.get("subtitle", "")),
        ),
        Fieldset(Legend(Tx("Authors")),
                 Textarea("\n".join(book.frontmatter.get("authors", [])),
                          name="authors", rows="3")),
    ]
    return (
        Title(f'{Tx("Edit")} {book.title}'),
        Header(nav(book=book, title=f'{Tx("Edit")} {book.title}'), cls="container"),
        Main(
            Form(*fields,
                 Button(Tx("Save")),
                 action=f"/{bid}/edit",
                 method="post"),
            cls="container",
        ),
    )


@rt("/{bid}/edit")
def post(bid:str, title:str, subtitle:str, authors:str):
    "Actually edit the book data."
    book = get_book(bid)
    if title:
        book.frontmatter["title"] = title
    else:
        book.frontmatter.pop("title", None)
    if subtitle:
        book.frontmatter["subtitle"] = subtitle
    else:
        book.frontmatter.pop("subtitle", None)
    if authors:
        authors = [a.strip() for a in authors.split("\n")]
    if authors:
        book.frontmatter["authors"] = authors
    else:
        book.frontmatter.pop("authors", None)
    book.write_index()
    return Redirect(f"/{bid}/title")


@rt("/{bid}/up/{path:path}")
def get(bid: str, path: str):
    "Move item up in its sibling list."
    book = get_book(bid)
    book[path].up()
    book.write_index()
    return Redirect(f"/{bid}/")


@rt("/{bid}/down/{path:path}")
def get(bid: str, path: str):
    "Move item down in its sibling list."
    book = get_book(bid)
    book[path].down()
    book.write_index()
    return Redirect(f"/{bid}/")


@rt("/{bid}/text/{path:path}")
def get(bid: str, path: str):
    "View the text."
    book = get_book(bid)
    text = book[path]
    assert text.is_text
    text.read()
    actions = [
        A(Tx("Edit"), href=f"/{bid}/edit/{path}"),
        A(Tx("Convert to section"), href=f"/{bid}/to_section/{path}"),
        A(f'{Tx("Download")} DOCX', href=f"/{bid}/docx/{path}"),
        A(f'{Tx("Delete")}', href=f"/{bid}/delete/{path}"),
    ]
    if text.frontmatter.get("suppress_title"):
        items = [H3(Del(text.heading))]
    else:
        items = [H3(text.heading)]
    return (
        Title(text.title),
        Header(nav(book=book, item=text, actions=actions), cls="container"),
        Main(*items, NotStr(text.html), cls="container"),
    )


@rt("/{bid}/edit/{path:path}")
def get(bid: str, path: str):
    "Page for editing the item (section or text)."
    book = get_book(bid)
    item = book[path]
    fields = [
        Fieldset(
            Label(Tx("Title")),
            Input(name="title", value=item.title, required=True, autofocus=True),
        )
    ]
    if item.is_text:
        item.read()
        fields.append(
            Fieldset(
                Legend(Tx("Title")),
                Label(
                    Input(
                        type="checkbox",
                        name="display_title",
                        role="switch",
                        checked=not(bool(item.frontmatter.get("suppress_title")))
                    ),
                    Tx("Display in output"),
                ),
            )
        )
        status_options = []
        for status in constants.STATUSES:
            if item.status == status:
                status_options.append(
                    Option(Tx(str(status)), selected=True, value=repr(status))
                )
            else:
                status_options.append(Option(Tx(str(status)), value=repr(status)))
        fields.append(
            Fieldset(
                Label(
                    Tx("Status"), Select(*status_options, name="status", required=True)
                )
            )
        )
        fields.append(Textarea(NotStr(item.content), name="content", rows="30"))
    fields.append(Button("Save"))
    return (
        Title(f'{Tx("Edit")} {item.fullname}'),
        Header(nav(book=book, title=f'{Tx("Edit")} {item.fullname}'), cls="container"),
        Main(
            Form(*fields, action=f"/{bid}/edit/{path}", method="post"),
            cls="container",
        ),
    )


@rt("/{bid}/edit/{path:path}")
def post(bid:str, path:str, title:str, content:str=None, display_title:bool=None, status:str=None):
    "Actually edit the item (section or text).."
    item = get_book(bid)[path]
    item.set_title(title)
    if item.is_text:
        ic(display_title)
        if display_title:
            item.frontmatter.pop("suppress_title", None)
        else:
            item.frontmatter["suppress_title"] = True
        if status is not None:
            item.status = status
        item.write(content=content)
        return Redirect(f"/{bid}/text/{item.urlpath}")
    else:
        return Redirect(f"/{bid}/section/{item.urlpath}")


@rt("/{bid}/delete/{path:path}")
def get(bid: str, path: str):
    "Confirm delete of the text, section or book; section and book must be empty."
    book = get_book(bid)
    if path == "":
        if len(book.items) != 0:
            return error("Cannot delete non-empty book.")
        item = None
        title = book.title
    else:
        item = book[path]
        title = item.title
        if item.is_section and len(item.items) != 0:
            return error("Cannot delete non-empty section.")
    return (
        Title(title),
        Header(nav(book=book, item=item, title=title), cls="container"),
        Main(
            H3(Tx("Delete"), "?"),
            Form(Button(Tx("Confirm")), action=f"/{bid}/delete/{path}", method="post"),
            cls="container",
        ),
    )


@rt("/{bid}/delete/{path:path}")
def post(bid: str, path: str):
    "Delete the text, section or book; section or book must be empty."
    book = get_book(bid)
    if path == "":
        if len(book.items) != 0:
            return error("Cannot delete non-empty book")
        try:
            os.remove(os.path.join(book.abspath, "index.md"))
        except OSError:
            pass
        books.pop(book.id)
        os.rmdir(book.abspath)
        return Redirect("/")
    else:
        item = book[path]
        try:
            book.delete(item)
        except ValueError as msg:
            return error(str(msg))
        return Redirect(f"/{bid}")


@rt("/{bid}/section/{path:path}")
def get(bid: str, path: str):
    "View the section."
    book = get_book(bid)
    section = book[path]
    assert section.is_section
    actions = [
        A(Tx("Edit"), href=f"/{bid}/edit/{path}"),
        A(f'{Tx("Create")} {Tx("section")}', href=f"/{bid}/create_section/{path}"),
        A(f'{Tx("Create")} {Tx("text")}', href=f"/{bid}/create_text/{path}"),
        A(f'{Tx("Download")} DOCX', href=f"/{bid}/docx/{path}"),
    ]
    if len(section.items) == 0:
        actions.append(A(f'{Tx("Delete")}', href=f"/{bid}/delete/{path}"))
    return (
        Title(section.title),
        Header(nav(book=book, item=section, actions=actions), cls="container"),
        Main(toc(book, section.items), cls="container"),
    )


@rt("/{bid}/to_section/{path:path}")
def get(bid: str, path: str):
    "Convert to section containing a text with this text."
    book = get_book(bid)
    text = book[path]
    assert text.is_text
    return (
        Title(Tx("Convert to section")),
        Header(nav(book=book, title=Tx("Convert to section")), cls="container"),
        Main(
            P(Tx("Text"), ": ", text.fullname),
            Form(
                Button(Tx("Convert")), action=f"/{bid}/to_section/{path}", method="post"
            ),
            cls="container",
        ),
    )


@rt("/{bid}/to_section/{path:path}")
def post(bid: str, path: str):
    "Convert to section containing a text with this text."
    text = get_book(bid)[path]
    assert text.is_text
    section = text.to_section()
    assert section.is_section
    return Redirect(f"/{bid}/section/{section.urlpath}")


@rt("/{bid}/create_text/{path:path}")
def get(bid: str, path: str):
    "Create a new text in the section."
    book = get_book(bid)
    assert path == "" or book[path].is_section
    title = f'{Tx("Create")} {Tx("text")}'
    return (
        Title(title),
        Header(nav(book=book, title=title), cls="container"),
        Main(
            Form(
                Fieldset(
                    Label(Tx("Title")),
                    Input(name="title", required=True, autofocus=True),
                ),
                Button(Tx("Create")),
                action=f"/{bid}/create_text/{path}",
                method="post",
            ),
            cls="container",
        ),
    )


@rt("/{bid}/create_text/{path:path}")
def post(bid: str, path: str, title: str = None):
    "Create a new text in the section."
    book = get_book(bid)
    if path == "":
        parent = None
    else:
        parent = book[path]
        assert parent.is_section
    new = book.create_text(title, parent=parent)
    if path:
        return Redirect(f"/{bid}/section/{path}")
    else:
        return Redirect(f"/{bid}")


@rt("/{bid}/create_section/{path:path}")
def get(bid: str, path: str):
    "Create a new section in the section."
    book = get_book(bid)
    assert path == "" or book[path].is_section
    title = f'{Tx("Create")} {Tx("section")}'
    return (
        Title(title),
        Header(nav(book=book, title=title), cls="container"),
        Main(
            Form(
                Fieldset(
                    Label(Tx("Title")),
                    Input(name="title", required=True, autofocus=True),
                ),
                Button(Tx("Create")),
                action=f"/{bid}/create_section/{path}",
                method="post",
            ),
            cls="container",
        ),
    )


@rt("/{bid}/create_section/{path:path}")
def post(bid: str, path: str, title: str = None):
    "Create a new section in the section."
    book = get_book(bid)
    if path == "":
        parent = None
    else:
        parent = book[path]
        assert parent.is_section
    new = book.create_section(title, parent=parent)
    if path:
        return Redirect(f"/{bid}/section/{path}")
    else:
        return Redirect(f"/{bid}")


@rt("/{bid}/title")
def get(bid: str):
    "Title page."
    book = get_book(bid)
    book.index.read()
    segments = [H1(book.title)]
    if book.subtitle:
        segments.append(H2(book.subtitle))
    for author in book.authors:
        segments.append(H3(author))
    segments.append(NotStr(book.index.html))
    return (
        Title(Tx("Title")),
        Header(
            nav(
                book=book,
                title=Tx("Title"),
                actions=[
                    A(f'{Tx("Edit")}', href=f"/{bid}/edit"),
                    A(f'{Tx("Download")} DOCX', href=f"/{bid}/docx"),
                    A(f'{Tx("Download")} PDF', href=f"/{bid}/pdf"),
                    A(f'{Tx("Download")} TGZ', href=f"/{bid}/tgz"),
                ],
            ),
            cls="container",
        ),
        Main(*segments, cls="container"),
    )


@rt("/{bid}/index")
def get(bid: str):
    "Page listing the indexed terms."
    book = get_book(bid)
    items = []
    for key, texts in sorted(book.indexed.items(), key=lambda tu: tu[0].lower()):
        links = []
        for text in sorted(texts, key=lambda t: t.ordinal):
            if links:
                links.append(NotStr(",&nbsp; "))
            links.append(
                A(text.fullname, cls="secondary", href=f"/{bid}/text/{text.fullname}")
            )
        items.append(Li(key, Br(), Small(*links)))
    return (
        Title(Tx("Index")),
        Header(nav(book=book, title=Tx("Index")), cls="container"),
        Main(Ul(*items), cls="container"),
    )


@rt("/{bid}/statuslist")
def get(bid: str):
    "Page listing each status and texts in it."
    book = get_book(bid)
    rows = [Tr(Th(Tx("Status"), Th(Tx("Texts"))))]
    for status in constants.STATUSES:
        texts = []
        for t in book.all_texts:
            if t.status == status:
                if texts:
                    texts.append(Br())
                texts.append(
                    A(
                        f"{'.'.join([str(o+1) for o in t.ordinal])}. {t.title}",
                        href=f"/{bid}/text/{t.urlpath}",
                    )
                )
        rows.append(Tr(Td(Tx(str(status)), valign="top"), Td(*texts)))
    return (
        Title(Tx("Status list")),
        Header(nav(book=book, title=Tx("Status list")), cls="container"),
        Main(Table(*rows), cls="container"),
    )


@rt("/{bid}/docx")
def get(bid: str):
    "Download the DOCX for the whole book."
    return get_docx(bid)


@rt("/{bid}/docx/{path:path}")
def get(bid: str, path: str):
    "Download the DOCX for a section or text in the book."
    return get_docx(bid, path)


def get_docx(bid, path=None):
    "Get the parameters for downloading the DOCX file."
    book = get_book(bid)
    if path:
        item = book[path]
    else:
        item = None
    settings = book.frontmatter.setdefault("docx", {})
    title_page_metadata = settings.get("title_page_metadata", True)
    page_break_level = settings.get("page_break_level", 1)
    page_break_options = []
    for value in range(0, 7):
        if value == page_break_level:
            page_break_options.append(Option(str(value), selected=True))
        else:
            page_break_options.append(Option(str(value)))
    footnotes_location = settings.get(
        "footnotes_location", constants.FOOTNOTES_EACH_TEXT
    )
    footnotes_options = []
    for value in constants.FOOTNOTES_LOCATIONS:
        if value == footnotes_location:
            footnotes_options.append(
                Option(Tx(value.capitalize()), value=value, selected=True)
            )
        else:
            footnotes_options.append(Option(Tx(value.capitalize()), value=value))
    reference_font = settings.get("reference_font", constants.NORMAL)
    reference_options = []
    for value in constants.FONT_STYLES:
        if value == reference_font:
            reference_options.append(
                Option(Tx(value.capitalize()), value=value, selected=True)
            )
        else:
            reference_options.append(Option(Tx(value.capitalize())))
    indexed_font = settings.get("indexed_font", constants.NORMAL)
    indexed_options = []
    for value in constants.FONT_STYLES:
        if value == indexed_font:
            indexed_options.append(
                Option(Tx(value.capitalize()), value=value, selected=True)
            )
        else:
            indexed_options.append(Option(Tx(value.capitalize()), value=value))
    fields = []
    if item is None:
        fields.append(
            Fieldset(
                Legend(Tx("Metadata on title page")),
                Label(
                    Input(
                        type="checkbox",
                        name="title_page_metadata",
                        role="switch",
                        checked=bool(title_page_metadata),
                    ),
                    Tx("Display on title page."),
                ),
            )
        )
    else:
        fields.append(Hidden(name="path", value=item.urlpath))
    fields.append(
        Fieldset(
            Legend(Tx("Page break level")),
            Select(*page_break_options, name="page_break_level"),
        )
    )
    if item is None:
        fields.append(
            Fieldset(
                Legend(Tx("Footnotes location")),
                Select(*footnotes_options, name="footnotes_location"),
            )
        )
    else:
        fields.append(Hidden(name="footnotes_location", value="after each text"))
    fields.append(
        Fieldset(
            Legend(Tx("Reference font")),
            Select(*reference_options, name="reference_font"),
        )
    )
    fields.append(
        Fieldset(
            Legend(Tx("Indexed font")), Select(*indexed_options, name="indexed_font")
        )
    )
    fields.append(Button(f'{Tx("Download")} DOCX'))

    if path is None:
        title = book.title
    else:
        title = path
    return (
        Title(f'{Tx("Download")} DOCX:  {title}'),
        Header(
            nav(book=book, title=f'{Tx("Download")} DOCX: {title}'), cls="container"
        ),
        Main(Form(*fields, action=f"/{bid}/docx", method="post"), cls="container"),
    )


@rt("/{bid}/docx")
def post(
    bid: str,
    path: str = None,
    title_page_metadata: bool = False,
    page_break_level: int = None,
    footnotes_location: str = None,
    reference_font: str = None,
    indexed_font: str = None,
):
    "Actually download the DOCX file of the book."
    book = get_book(bid)
    if path:
        path = urllib.parse.unquote(path)
        item = book[path]
    else:
        item = None
    original = copy.deepcopy(book.frontmatter)
    settings = book.frontmatter.setdefault("docx", {})
    settings["title_page_metadata"] = title_page_metadata
    settings["page_break_level"] = page_break_level
    settings["footnotes_location"] = footnotes_location
    settings["reference_font"] = reference_font
    settings["indexed_font"] = indexed_font
    if item is None:
        if book.frontmatter != original:
            book.index.write()
        filename = book.title + ".docx"
    else:
        filename = item.title + ".docx"
    creator = docx_creator.Creator(book, get_references(), item=item)
    output = creator.create()
    return Response(
        content=output.getvalue(),
        media_type=constants.DOCX_MIMETYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@rt("/{bid}/pdf")
def pdf(bid: str):
    "Get the parameters for downloading PDF file of the whole book."
    book = get_book(bid)
    settings = book.frontmatter.setdefault("pdf", {})
    title_page_metadata = settings.get("title_page_metadata", True)
    page_break_level = settings.get("page_break_level", 1)
    page_break_options = []
    for value in range(0, 7):
        if value == page_break_level:
            page_break_options.append(Option(str(value), selected=True))
        else:
            page_break_options.append(Option(str(value)))
    contents_pages = settings.get("contents_pages", True)
    contents_level = settings.get("contents_level", 1)
    contents_level_options = []
    for value in range(0, 7):
        if value == contents_level:
            contents_level_options.append(Option(str(value), selected=True))
        else:
            contents_level_options.append(Option(str(value)))

    footnotes_location = settings.get(
        "footnotes_location", constants.FOOTNOTES_EACH_TEXT
    )
    footnotes_options = []
    for value in constants.FOOTNOTES_LOCATIONS:
        if value == footnotes_location:
            footnotes_options.append(
                Option(Tx(value.capitalize()), value=value, selected=True)
            )
        else:
            footnotes_options.append(Option(Tx(value.capitalize()), value=value))

    indexed_xref = settings.get("indexed_xref", constants.PDF_PAGE_NUMBER)
    indexed_options = []
    for value in constants.PDF_INDEXED_XREF_DISPLAY:
        if value == indexed_xref:
            indexed_options.append(
                Option(Tx(value.capitalize()), value=value, selected=True)
            )
        else:
            indexed_options.append(Option(Tx(value.capitalize()), value=value))

    return (
        Title(f'{Tx("Download")} PDF'),
        Header(nav(book=book, title=f'{Tx("Download")} PDF'), cls="container"),
        Main(
            Form(
                Fieldset(
                    Legend(Tx("Metadata on title page")),
                    Label(
                        Input(
                            type="checkbox",
                            name="title_page_metadata",
                            role="switch",
                            checked=bool(title_page_metadata),
                        ),
                        Tx("Display on title page."),
                    ),
                ),
                Fieldset(
                    Legend(Tx("Page break level")),
                    Select(*page_break_options, name="page_break_level"),
                ),
                Fieldset(
                    Legend(Tx("Contents pages")),
                    Label(
                        Input(
                            type="checkbox",
                            name="contents_pages",
                            role="switch",
                            checked=bool(contents_pages),
                        ),
                        Tx("Display in output"),
                    ),
                ),
                Fieldset(
                    Legend(Tx("Contents level")),
                    Select(*contents_level_options, name="contents_level"),
                ),
                Fieldset(
                    Legend(Tx("Footnotes location")),
                    Select(*footnotes_options, name="footnotes_location"),
                ),
                Fieldset(
                    Legend(Tx("Display of indexed term reference")),
                    Select(*indexed_options, name="indexed_xref"),
                ),
                Button(f'{Tx("Download")} PDF'),
                action=f"/{bid}/pdf",
                method="post",
            ),
            cls="container",
        ),
    )


@rt("/{bid}/pdf")
def post(
    bid: str,
    title_page_metadata: bool = False,
    page_break_level: int = None,
    contents_pages: bool = False,
    contents_level: int = None,
    footnotes_location: str = None,
    indexed_xref: str = None,
):
    "Actually download the PDF file of the book."
    book = get_book(bid)
    original = copy.deepcopy(book.frontmatter)
    settings = book.frontmatter.setdefault("pdf", {})
    settings["title_page_metadata"] = title_page_metadata
    settings["page_break_level"] = page_break_level
    settings["contents_pages"] = contents_pages
    settings["contents_level"] = contents_level
    settings["footnotes_location"] = footnotes_location
    settings["indexed_xref"] = indexed_xref
    if book.frontmatter != original:
        book.index.write()
    filename = book.title + ".pdf"
    creator = pdf_creator.Creator(book, get_references())
    output = creator.create()
    return Response(
        content=output.getvalue(),
        media_type=constants.PDF_MIMETYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@rt("/{bid}/tgz")
def get(bid: str):
    "Download a gzipped tar file of the book."
    book = get_book(bid)
    filename = f"{book.title} {utils.timestr()}.tgz"
    output = book.archive()
    return Response(
        content=output.getvalue(),
        media_type=constants.GZIP_MIMETYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


serve()
