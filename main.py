"Web view and edit of Markdown book contents."

from icecream import ic

import copy
import os
import string
import sys
import time
import urllib

from fasthtml.common import *
import bibtexparser
import yaml

import constants
import docx_creator
import pdf_creator
import utils

from book import read_frontmatter, Book

NAV_STYLE_TEMPLATE = "outline-color: {color}; outline-width:8px; outline-style:solid; padding:0px 10px; border-radius:5px;"

Tx = utils.Tx

try:
    MDBOOKS = os.environ["MDBOOKS"]
except KeyError:
    if len(sys.argv) == 2:
        MDBOOKS = sys.argv[1]
    else:
        MDBOOKS = os.getcwd()

# XXX 'static_path' does not seem to do its job?
app, rt = fast_app(live=True, static_path=constants.SOURCE_DIRPATH)


# Key: bid; value: Book instance.
books = {}

def get_book(bid):
    "Get the book contents, cached."
    try:
        return books[bid]
    except KeyError:
        book = Book(os.path.join(MDBOOKS, bid))
        books[bid] = book
        return book

def get_references():
    "Get the references book, cached."
    global _references
    try:
        return_references
    except NameError:
        _references = Book(os.path.join(MDBOOKS, constants.REFERENCES_DIR))
        return _references


def nav(book=None, item=None, title=None, actions=None):
    "The standard navigation bar."
    if book is None:
        entries = [Ul(Li(A(Img(src="/mdbook.svg"), href="/")))]
    else:
        entries = [Ul(Li(A(Img(src="/mdbook.svg"), href="/")),
                      Li(A(book.title, href=f"/{book.id}")))]
    if item:
        entries.append(Ul(Li(Strong(item.fullname),
                             Br(),
                             Small(f'{Tx("Status")}: {Tx(item.status)}'))))
        nav_style = NAV_STYLE_TEMPLATE.format(color=item.status.color)
    elif title:
        entries.append(Ul(Li(title)))
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
            if item.parent.level == 0: # Book.
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
        pages.extend([A(Tx("Title"), href=f"/{book.id}/title"),
                      A(Tx("Index"), href=f"/{book.id}/index"),
                      A(Tx("Statuses"), href=f"/{book.id}/statuses")])
    pages.append(A(Tx("References"), href="/references"))
    items = []
    if len(pages) == 1:
        if title != Tx("References"):
            items.append(Ul(Li(pages[0], NotStr("&nbsp;"))))
    else:
        items.append(Li(Details(Summary(Tx("Pages")),
                                Ul(*[Li(p) for p in pages]),
                                cls="dropdown")))
    if actions:
        items.append(Li(Details(Summary(Tx("Actions")),
                                Ul(*[Li(c) for c in actions]),
                                cls="dropdown")))
    if items:
        entries.append(Ul(*items))
    return Nav(*entries, style=nav_style)

def toc(book, items, show_arrows=False):
    "Recursive lists of sections and texts."
    parts = []
    for item in items:
        n_words = f"{utils.thousands(item.n_words)}"
        n_characters = f"{utils.thousands(len(item))}"
        data = f'{Tx(item.status)}; {n_words} {Tx("words")}; {n_characters} {Tx("characters")}'
        if show_arrows:
            arrows = [NotStr("&nbsp;"),
                      A(NotStr("&ShortUpArrow;"), href=f"/up/{item.urlpath}"),
                      NotStr("&nbsp;"),
                      A(NotStr("&ShortDownArrow;"), href=f"/down/{item.urlpath}")]
        else:
            arrows = []
        if item.is_section:
            parts.append(Li(A(str(item),
                              style=f"color: {item.status.color};",
                              href=f"/section/{item.urlpath}"),
                            NotStr("&nbsp;&nbsp;&nbsp;"),
                            Small(data, style="color: silver;"),
                            *arrows,
                            style=f"color: {item.status.color};",))
            parts.append(toc(book, item.items, show_arrows=show_arrows))
        else:
            parts.append(Li(A(str(item),
                              style=f"color: {item.status.color};",
                              href=f"/text/{item.urlpath}"),
                            NotStr("&nbsp;&nbsp;&nbsp;"),
                            Small(data, style="color: silver;"),
                            *arrows))
    return Ol(*parts)

@rt("/")
def home():
    "Home page; list of books."
    books = []
    for bid in os.listdir(MDBOOKS):
        if bid == constants.REFERENCES_DIR:
            continue
        try:
            dirpath = os.path.join(MDBOOKS, bid)
            filepath = os.path.join(dirpath, "index.md")
            with open(filepath) as infile:
                frontmatter, content = read_frontmatter(infile.read())
            books.append({"bid": bid,
                          "title": frontmatter.get("title", bid),
                          "dirpath": dirpath,
                          "authors": frontmatter.get("authors", []),
                          "modified": time.strftime(constants.DATETIME_ISO_FORMAT,
                                                    time.localtime(os.path.getmtime(filepath)))})
        except OSError:
            pass
    books.sort(key=lambda b: b["modified"], reverse=True)
    rows = []
    for book in books:
        rows.append(Tr(Td(A(book["title"], href=f'/{book["bid"]}')),
                       Td(book["modified"])))
    return (Title("mdbooks"),
            Header(nav(title="mdbooks"), cls="container"),
            Main(Table(*rows), cls="container")
            )

@rt("/references")
def references():
    "Page for list of references."
    references = get_references()
    references.read()
    items = []
    for ref in references.items:
        parts = [Img(src="/clipboard.svg",
                     title="Refid to clipboard",
                     style="cursor: pointer;",
                     cls="to_clipboard", 
                     data_clipboard_text=f'[@{ref["id"]}]'),
                 NotStr("&nbsp;"),
                 A(Strong(ref["id"], style="color: royalblue;"),
                   href=f'/reference/{ref["id"].replace(" ", "_")}'),
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
                links.append(A(f'{symbol}:{ref["isbn"]}', 
                               href=url.format(value=ref["isbn"])))

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
            links.append(A(f'{symbol}:{ref["doi"]}', 
                           href=url.format(value=ref["doi"])))
        if ref.get("pmid"):
            symbol, url = constants.REFERENCE_LINKS["pmid"]
            url = url.format(value=ref["pmid"])
            if links:
                links.append(", ")
            links.append(A(f'{symbol}:{ref["pmid"]}', 
                           href=url.format(value=ref["pmid"])))

        if links:
            parts.append(" ")
            parts.extend(links)

        # XXX
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

    return (Title(Tx("References")),
            Header(nav(title=Tx("References"),
                       actions=[A(Tx("Add BibTex"), href="/bibtex")]),
                   cls="container"),
            Main(*items, cls="container")
            )

@rt("/reference/{refid:str}")
def get(refid:str):
    "Page for details of a reference."
    ref = get_references()[refid.replace("_", " ")]
    rows = [Tr(Td(Tx("Identifier")),
               Td(f'{ref["id"]}',
                  NotStr("&nbsp;"),
                  Img(src="/clipboard.svg",
                      title="Refid to clipboard",
                      style="cursor: pointer;",
                      cls="to_clipboard", 
                      data_clipboard_text=f'[@{ref["id"]}]'))
               ),
            Tr(Td(Tx("Authors")), Td("; ".join(ref.get("authors") or [])))
            ]
    for key in ["year", "title", "subtitle", "type", "edition_published", "language",
                "date", "keywords", "journal", "volume", "number", "pages",
                "publisher", "source"]:
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
    return (Title(refid),
            Script(src="/clipboard.min.js"),
            Script("new ClipboardJS('.to_clipboard');"),
            Header(nav(title=ref["id"],
                       actions=[A(Tx("Clipboard"),
                                  href="#",
                                  cls="to_clipboard", 
                                  data_clipboard_text=f'[@{ref["id"]}]'),
                                ]),
                   cls="container"),
            Main(Table(*rows),
                 Div(NotStr(ref.html)),
                 cls="container"))

@rt("/bibtex", methods=["get", "post"])
def bibtex(data:str=None):
    "Page for adding a reference using BibTex data."
    result = []
    if data:
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
                new["keywords"] = [
                    k.strip() for k in new["keywords"].split(";")
                ]
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
        return (Title("Added reference(s)"),
                Header(nav(title="Added reference(s)"), cls="container"),
                Main(Ul(
                    *[Li(A(r["id"], href=f'/reference/{r["id"]}')) for r in result]),
                     cls="container")
                )
    else:
        return (Title("Add reference"),
                Header(nav(title="Add reference"), cls="container"),
                Main(Form(
                    Fieldset(
                        Legend("Bibtex data"),
                        Textarea(name="data", rows="20")
                    ),
                    Button("Add"),
                    action=f"/bibtex",
                    method="post"),
                     cls="container")
                )

@rt("/{bid}")
def get(bid:str):
    "Book home page; list of sections and texts."
    book = get_book(bid)
    book.read()
    return (Title(book.title),
            Header(nav(book=book,
                       actions=[A(f'{Tx("Statuses")}', href=f"/{bid}/statuses"),
                                A(f'{Tx("Create")} {Tx("section")}',
                                  href=f"/{bid}/create_section"),
                                A(f'{Tx("Create")} {Tx("text")}',
                                  href=f"/{bid}/create_text"),
                                A(f'{Tx("Create")} DOCX', href=f"/{bid}/docx"),
                                A(f'{Tx("Create")} PDF', href=f"/{bid}/pdf"),
                                A(f'{Tx("Create")} TGZ', href=f"/{bid}/tgz"),
                                ]),
                   cls="container"),
            Main(toc(book, book.items, show_arrows=True), cls="container")
            )

@rt("/{bid}/up/{path:path}")
def get(bid:str, path:str):
    "Move item up in its sibling list."
    book = get_book(bid)
    book[path].up()
    book.write_index()
    return Redirect(f"/{bid}/")

@rt("/{bid}/down/{path:path}")
def get(bid:str, path:str):
    "Move item down in its sibling list."
    book = get_book(bid)
    book[path].down()
    book.write_index()
    return Redirect(f"/{bid}/")

@rt("/{bid}/text/{path:path}")
def get(bid:str, path:str):
    "View the text, or edit title, content or status and save."
    text = get_book(bid)[path]
    assert text.is_text
    text.read()
    return (Title(text.title),
            Header(nav(item=text,
                       actions=[A(Tx("Edit"), href=f"/{bid}/edit/{path}"),
                                A(Tx("Convert to section"), 
                                  href=f"/{bid}/to_section/{path}"),
                                A(f'{Tx("Create")} DOCX', href=f"/{bid}/docx/{path}")]),
                   cls="container"),
            Main(NotStr(text.html), cls="container")
            )

@rt("/{bid}/edit/{path:path}")
def get(bid:str, path:str):
    "Edit the item (section or text)."
    item = get_book(bid)[path]
    fields = [
        Fieldset(
            Label(Tx("New title")),
                  Input(name="title", value=item.title, required=True))
    ]
    if item.is_text:
        item.read()
        status_options = []
        for status in constants.STATUSES:
            if item.status == status:
                status_options.append(Option(Tx(str(status)),
                                             selected=True, 
                                             value=repr(status)))
            else:
                status_options.append(Option(Tx(str(status)), value=repr(status)))
        fields.append(
            Fieldset(Label(Tx("Status"),
                           Select(*status_options, name="status", required=True)))
        )
        fields.append(Textarea(NotStr(item.content), name="content", rows="30"))
    fields.append(Button("Save"))
    return (Title(f'{Tx("Edit")} {item.fullname}'),
            Header(nav(title=f'{Tx("Edit")} {item.fullname}'), cls="container"),
            Main(Form(*fields, action=f"{bid}//change/{path}", method="post"),
                 cls="container"),
            )

@rt("/{bid}/change/{path:path}")
def post(bid:str, path:str, title:str, content:str=None, status:str=None):
    "Change the title of the section, or content and status of the text and save."
    item = get_book(bid)[path]
    item.new_title(title)
    if item.is_text:
        if status is not None:
            item.status = status
        item.write(content=content)
        return Redirect(f"/{bid}/text/{item.urlpath}")
    else:
        return Redirect(f"/{bid}/section/{item.urlpath}")

@rt("/{bid}/section/{path:path}")
def get(bid:str, path:str):
    "View the section."
    book = get_book(bid)
    section = book[path]
    assert section.is_section
    return (Title(section.title),
            Header(nav(item=section,
                       actions=[A(Tx("Edit"), href=f"/{bid}/edit/{path}"),
                                A(f'{Tx("Create")} {Tx("section")}',
                                  href=f"/{bid}/create_section/{path}"),
                                A(f'{Tx("Create")} {Tx("text")}',
                                  href=f"/{bid}/create_text/{path}"),
                                A(f'{Tx("Create")} DOCX', href=f"/{bid}/docx/{path}")]),
                   cls="container"),
            Main(toc(book, section.items), cls="container")
            )

@rt("/{bid}/to_section/{path:path}")
def get(bid:str, path:str):
    "Convert to section containing a text with a new title out of this text."
    text  = get_book(bid)[path]
    assert text.is_text
    return (Title(Tx("Convert to section")),
            Header(nav(title=Tx("Convert to section")), cls="container"),
            Main(P(Tx("Text"), ": ", text.fullname),
                 Form(Button(Tx("Make")),
                      action=f"/{bid}/to_section/{path}",
                      method="post"),
                 cls="container"),
            )

@rt("/{bid}/to_section/{path:path}")
def post(bid:str, path:str):
    "Convert to section containing a text with a new title out of this text."
    text  = get_book(bid)[path]
    assert text.is_text
    section = text.to_section()
    assert section.is_section
    return Redirect(f"/{bid}/section/{section.urlpath}")

@rt("/{bid}/create_text/{path:path}")
def get(bid:str, path:str):
    "Create a new text in the section."
    assert get_book(bid)[path].is_section
    return (Title(Tx("Create text")),
            Header(nav(title=Tx("Create text")), cls="container"),
            Main(Form(
                Fieldset(
                    Label(Tx("Title")),
                    Input(name="title", required=True)),
                Button(Tx("Create")),
                      action=f"/{bid}/create_text/{path}",
                      method="post"),
                 cls="container"),
            )

@rt("/{bid}/create_text/{path:path}")
def post(bid:str, path:str, title:str=None):
    "Create a new text in the section."
    book = get_book(bid)
    section = book[path]
    assert section.is_section
    new = book.create_text(title, anchor=section)
    return Redirect(f"/{bid}/section/{path}")

@rt("/{bid}/create_section/{path:path}")
def get(bid:str, path:str):
    "Create a new section in the section."
    "Create a new text in the section."
    assert get_book(bid)[path].is_section
    return (Title(Tx("Create section")),
            Header(nav(title=Tx("Create section")), cls="container"),
            Main(Form(
                Fieldset(
                    Label(Tx("Title")),
                    Input(name="title", required=True)),
                Button(Tx("Create")),
                      action=f"/{bid}/create_section/{path}",
                      method="post"),
                 cls="container"),
            )

@rt("/{bid}/create_section/{path:path}")
def post(bid:str, path:str, title:str=None):
    "Create a new section in the section."
    book = get_book(bid)
    section = book[path]
    assert section.is_section
    new = book.create_section(title, anchor=section)
    return Redirect(f"/{bid}/section/{path}")

@rt("/{bid}/title")
def title_page(bid:str):
    "Title page."
    book = get_book(bid)
    book.index.read()
    segments = [H1(book.title)]
    if book.subtitle:
        segments.append(H2(book.subtitle))
    for author in book.authors:
        segments.append(H3(author))
    segments.append(P(f'{utils.thousands(book.n_words)} {Tx("words")},'
                      f' {utils.thousands(len(book))} {Tx("characters")}.'))
    segments.append(P(f'{Tx("Language")}: {book.frontmatter.get("language", "-")}'))
    segments.append(NotStr(book.index.html))
    return (Title(Tx("Title")),
            Header(nav(book=book,
                       title=Tx("Title"),
                       actions=[A(f'{Tx("Create")} DOCX', href="/{bid}/docx"),
                                A(f'{Tx("Create")} PDF', href="/{bid}/pdf"),
                                A(f'{Tx("Create")} TGZ', href="/{bid}/tgz"),
                                ]),
                   cls="container"),
            Main(*segments, cls="container")
            )

@rt("/{bid}/index")
def index(bid:str):
    "Page listing the indexed terms."
    book = get_book(bid)
    items = []
    for key, texts in sorted(book.indexed.items(), key=lambda tu: tu[0].lower()):
        links = []
        for text in sorted(texts, key=lambda t: t.ordinal):
            if links:
                links.append(NotStr(",&nbsp; "))
            links.append(A(text.fullname, cls="secondary",
                           href=f"/{bid}/text/{text.fullname}"))
        items.append(Li(key, Br(), Small(*links)))
    return (Title(Tx("Index")),
            Header(nav(book=book, title=Tx("Index")), cls="container"),
            Main(Ul(*items), cls="container")
            )

@rt("/{bid}/statuses")
def statuses(bid:str):
    "Page listing the statuses and texts in them."
    book = get_book(bid)
    rows = [Tr(Th(Tx("Status"), Th(Tx("Texts"))))]
    for status in constants.STATUSES:
        texts = []
        for t in book.all_texts:
            if t.status == status:
                if texts:
                    texts.append(Br())
                texts.append(A(f"{'.'.join([str(o+1) for o in t.ordinal])}. {t.title}",
                               href=f"/{bid}/text/{t.urlpath}"))
        rows.append(Tr(Td(Tx(str(status)), valign="top"),
                       Td(*texts)))
    return (Title(Tx("Statuses")),
            Header(nav(book=book, title=Tx("Statuses")), cls="container"),
            Main(Table(*rows), cls="container")
            )

@rt("/{bid}/docx")
def docx(bid:str):
    "DOCX for the whole book."
    return get_docx(bid)

@rt("/{bid}/docx/{path:path}")
def docx(bid:str, path:str):
    "DOCX for a section or text in the book."
    return get_docx(bid, path)

def get_docx(bid, path=None):
    "Get the parameters for outputting DOCX file."
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
    footnotes_location = settings.get("footnotes_location", constants.FOOTNOTES_EACH_TEXT)
    footnotes_options = []
    for value in constants.FOOTNOTES_LOCATIONS:
        if value == footnotes_location:
            footnotes_options.append(Option(Tx(value.capitalize()),
                                            value=value, selected=True))
        else:
            footnotes_options.append(Option(Tx(value.capitalize()), value=value))
    reference_font = settings.get("reference_font", constants.NORMAL)
    reference_options = []
    for value in constants.FONT_STYLES:
        if value == reference_font:
            reference_options.append(Option(Tx(value.capitalize()),
                                            value=value, selected=True))
        else:
            reference_options.append(Option(Tx(value.capitalize())))
    indexed_font = settings.get("indexed_font", constants.NORMAL)
    indexed_options = []
    for value in constants.FONT_STYLES:
        if value == indexed_font:
            indexed_options.append(Option(Tx(value.capitalize()), 
                                          value=value, selected=True))
        else:
            indexed_options.append(Option(Tx(value.capitalize()),
                                          value=value))
    fields = []
    if item is None:
        fields.append(
            Fieldset(
                Legend(Tx("Metadata on title page")),
                Label(
                    Input(type="checkbox",
                          name="title_page_metadata",
                          role="switch",
                          checked=bool(title_page_metadata)),
                    Tx("Display")
                )
            )
        )
    else:
        fields.append(Hidden(name="path", value=item.urlpath))
    fields.append(
        Fieldset(
            Legend(Tx("Page break level")),
            Select(*page_break_options, name="page_break_level")
        )
    )
    if item is None:
        fields.append(
            Fieldset(
                Legend(Tx("Footnotes location")),
                Select(*footnotes_options, name="footnotes_location")
            )
        )
    else:
        fields.append(Hidden(name="footnotes_location", value="after each text"))
    fields.append(
        Fieldset(
            Legend(Tx("Reference font")),
            Select(*reference_options, name="reference_font")
        )
    )
    fields.append(
        Fieldset(
            Legend(Tx("Indexed font")),
            Select(*indexed_options, name="indexed_font")
        )
    )
    fields.append(
        Button(f'{Tx("Create")} DOCX')
    )
    
    if path is None:
        title = book.title
    else:
        title = path
    return (Title(f'{Tx("Create")} DOCX:  {title}'),
            Header(nav(book=book, title=f'{Tx("Create")} DOCX: {title}'),
                   cls="container"),
            Main(Form(*fields, action=f"/{bid}/docx_create", method="post"),
                 cls="container")
            )

@rt("/{bid}/docx_create")
def post(bid:str,
         path:str=None,
         title_page_metadata:bool=False,
         page_break_level:int=None,
         footnotes_location:str=None,
         reference_font:str=None,
         indexed_font:str=None):
    "Actually create and return the DOCX file."
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
        paras = []
    else:
        filename = item.title + ".docx"
        paras = [P(f'{Tx("Text")}: {path}')]
    creator = docx_creator.Creator(book, get_references(), item=item)
    output = creator.create()
    return Response(status_code=200,
                    content=output.getvalue(),
                    media_type=constants.DOCX_MIMETYPE,
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})

@rt("/{bid}/pdf")
def pdf(bid:str):
    "Get the parameters for outputting PDF file of the whole book."
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

    footnotes_location = settings.get("footnotes_location",
                                      constants.FOOTNOTES_EACH_TEXT)
    footnotes_options = []
    for value in constants.FOOTNOTES_LOCATIONS:
        if value == footnotes_location:
            footnotes_options.append(Option(Tx(value.capitalize()), value=value, selected=True))
        else:
            footnotes_options.append(Option(Tx(value.capitalize()), value=value))

    indexed_xref = settings.get("indexed_xref", constants.PDF_PAGE_NUMBER)
    indexed_options = []
    for value in constants.PDF_INDEXED_XREF_DISPLAY:
        if value == indexed_xref:
            indexed_options.append(Option(Tx(value.capitalize()), value=value, selected=True))
        else:
            indexed_options.append(Option(Tx(value.capitalize()), value=value))

    return (Title(f'{Tx("Create")} PDF'),
            Header(nav(book=book, title=f'{Tx("Create")} PDF'), cls="container"),
            Main(Form(
                Fieldset(
                    Legend(Tx("Metadata on title page")),
                    Label(
                        Input(type="checkbox",
                              name="title_page_metadata",
                              role="switch",
                              checked=bool(title_page_metadata)),
                        Tx("Display")
                    )
                ),
                Fieldset(
                    Legend(Tx("Page break level")),
                    Select(*page_break_options, name="page_break_level"),
                ),
                Fieldset(
                    Legend(Tx("Contents pages")),
                    Label(
                        Input(type="checkbox",
                              name="contents_pages",
                              role="switch",
                              checked=bool(contents_pages)),
                        Tx("Display")
                    )
                ),
                Fieldset(
                    Legend(Tx("Contents level")),
                    Select(*contents_level_options, name="contents_level"),
                ),
                Fieldset(
                    Legend(Tx("Footnotes location")),
                    Select(*footnotes_options, name="footnotes_location")
                ),
                Fieldset(
                    Legend(Tx("Display of indexed term reference")),
                    Select(*indexed_options, name="indexed_xref")
                ),
                Button(f'{Tx("Create")} PDF'),
                action=f"/{bid}/pdf_create",
                method="post"),
                 cls="container")
            )

@rt("/{bid}/pdf_create")
def post(bid:str,
         title_page_metadata:bool=False,
         page_break_level:int=None,
         contents_pages:bool=False,
         contents_level:int=None,
         footnotes_location:str=None,
         indexed_xref:str=None):
    "Actually create and return the PDF file."
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
    return Response(status_code=200,
                    content=output.getvalue(),
                    media_type=constants.PDF_MIMETYPE,
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})

@rt("/{bid}/tgz")
def tgz(bid:str):
    "Create an archive file of the book and return."
    book = get_book(bid)
    timestr = time.strftime(constants.DATETIME_ISO_FORMAT, time.localtime())
    filename = f"{book.title} {timestr}.tgz"
    output = book.archive()
    return Response(status_code=200,
                    content=output.getvalue(),
                    media_type=constants.GZIP_MIMETYPE,
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


serve()
