"View of Markdown book contents."

from icecream import ic

import os.path

from fasthtml.common import *

import constants
from book import Book
from translator import Translator


ABSDIRPATH = "/home/pekrau/Dropbox/texter/lejonen"

NAV_STYLE = "outline-color: {color}; outline-width:8px; outline-style:solid; padding:0px 10px; border-radius:5px;"


app, rt = fast_app(live=True)

Tx = Translator(constants.TRANSLATIONS_FILE)

def get_book(reload=False):
    "Get the book contents, cached."
    global _book
    if reload:
        try:
            del _book
        except NameError:
            pass
    try:
        return _book
    except NameError:
        ic("reloading book")
        _book = Book(ABSDIRPATH)
        return _book

def get_references(reload=False):
    "Get the references book, cached."
    global _references
    absdirpath = os.path.join(ABSDIRPATH, constants.REFERENCES_DIRNAME)
    if reload:
        try:
            del _references
        except NameError:
            pass
    try:
        return _references
    except NameError:
        ic("reloading references")
        _references = Book(absdirpath)
        return _references


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

def nav(item=None, label=None, commands=None):
    "The standard navigation bar."
    entries = [Ul(Li(Img(src="/favicon.ico")),
                  Li(A(get_book().title, href="/")))]
    if item:
        entries.append(Ul(Li(item.fullname,
                             Br(),
                             Small(f'{Tx("Status")}: {Tx(item.status)}'))))
        nav_style = NAV_STYLE.format(color=item.status.color)
    elif label:
        entries.append(Ul(Li(label)))
        nav_style = NAV_STYLE.format(color=get_book().status.color)
    else:
        entries.append(Ul(Li(f"Status: {Tx(get_book().status)}")))
        nav_style = NAV_STYLE.format(color=get_book().status.color)
    items = [Li(A(Tx("Title"), href="/title")),
             Li(A(Tx("Index"), href="/index")),
             Li(A(Tx("References"), href="/references"))]
    if commands:
        items.append(Li(Details(Summary(Tx("Commands")),
                                Ul(*[Li(c) for c in commands], dir="rtl"),
                                cls="dropdown")))
    entries.append(Ul(*items))
    return Nav(*entries, style=nav_style)

def contents(items):
    "Recursive lists of sections and texts."
    parts = []
    for item in items:
        n_words = f"{thousands(item.n_words)}"
        n_characters = f"{thousands(len(item))}"
        length = f'{n_words} {Tx("words")}; {n_characters} {Tx("characters")}'
        if item.is_section:
            parts.append(Li(str(item),
                            NotStr("&nbsp;&nbsp;&nbsp;"),
                            Small(length, style="color: silver;"),
                            style=f"color: {item.status.color};",))
            parts.append(contents(item.items))
        else:
            parts.append(Li(A(str(item),
                              style=f"color: {item.status.color};",
                              href=f"/text/{item.urlpath}"),
                            NotStr("&nbsp;&nbsp;&nbsp;"),
                            Small(length, style="color: silver;")))
    return Ol(*parts)

@rt("/")
def get(reload:str=None):
    "Home page; index of sections and texts."
    return (Title("mdbook"),
            Header(nav(commands=[A(Tx("Update"), href="/?reload=yes")]), cls="container"),
            Main(contents(get_book(reload=reload).items), cls="container")
            )

@rt("/text/{path:path}")
def get(path:str):
    "View the text."
    text = get_book()[path]
    text.read()
    return (Title(text.title),
            Header(nav(text), cls="container"),
            Main(NotStr(text.html), cls="container")
            )

@rt("/title")
def get():
    "Title page."
    segments = [H1(get_book().title)]
    if get_book().subtitle:
        segments.append(H2(get_book().subtitle))
    for author in get_book().authors:
        segments.append(H3(author))
    segments.append(Table(
        Tr(Th(Tx("Words")), Td(thousands(get_book().n_words))),
        Tr(Th(Tx("Characters")), Td(thousands(len(get_book()))))
    ))
    return (Title(Tx("Title")),
            Header(nav(label=Tx("Title")), cls="container"),
            Main(*segments, cls="container")
            )

@rt("/index")
def get():
    "Index page."
    items = []
    for key, texts in sorted(get_book().indexed.items(), key=lambda tu: tu[0].lower()):
        links = []
        for text in sorted(texts, key=lambda t: t.ordinal):
            if links:
                links.append(Br())
            links.append(A(text.fullname, href=f"/text/{text.fullname}"))
        items.append(Li(Strong(key), Br(), Small(*links)))
    return (Title(Tx("Index")),
            Header(nav(label=Tx("Index")), cls="container"),
            Main(Ul(*items), cls="container")
            )

@rt("/references")
def get(reload:str=None):
    "List of references."
    items = []
    for ref in get_references(reload=reload).items:
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
            authors = [short_name(a) for a in ref["authors"]]
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
        elif ref.get("type") == "link":
            parts.append(Br())
            parts.append(A(ref["url"], href=ref["url"]))
            if ref.get("accessed"):
                parts.append(f'(Accessed: {ref["accessed"]})')

        texts = get_book().references.get(ref["id"], [])
        links = []
        for text in sorted(texts, key=lambda t: t.ordinal):
            if links:
                links.append(Br())
            links.append(A(text.fullname, href=f"/text/{text.fullname}"))
        parts.append(Small(Br(), *links))
        items.append(P(*parts, id=ref["id"].replace(" ", "_")))
    return (Title(Tx("References")),
            Script(src="/clipboard.min.js"),
            Script("new ClipboardJS('.to_clipboard');"),
            Header(nav(label=Tx("References"),
                       commands=[A(Tx("Update"), href="/references?reload=yes"),
                                 ]),
                   cls="container"),
            Main(*items, cls="container")
            )

@rt("/reference/{refid:str}")
def get(refid:str, reload:str=None):
    "Reference details."
    ref = get_references(reload)[refid.replace("_", " ")]
    rows = [Tr(Td(Tx("Authors")), Td("; ".join(ref.get("authors") or [])))]
    for key in ["year", "title", "type", "edition_published", "language", "date",
                "keywords", "journal", "volume", "number", "pages", "publisher"]:
        value = ref.get(key)
        if value:
            rows.append(Tr(Td((Tx(key.replace("_", " ")).title())), Td(value)))
    if ref.get("issn"):
        rows.append(Tr(Td("ISSN"), Td(ref["issn"])))
    if ref.get("isbn"):
        rows.append(Tr(Td("ISBN"),
                       Td(A(ref["isbn"],
                            href=constants.ISBN.format(value=ref["isbn"])))))
    if ref.get("pmid"):
        rows.append(Tr(Td("PubMed"),
                       Td(A(ref["pmid"],
                            href=constants.PUBMED.format(value=ref["pmid"])))))
    if ref.get("doi"):
        rows.append(Tr(Td("DOI"),
                       Td(A(ref["doi"],
                            href=constants.DOI.format(value=ref["doi"])))))
    if ref.get("url"):
        rows.append(Tr(Td("Url"),
                       Td(A(ref["url"], href=ref["url"]))))
    return (Title(refid),
            Script(src="/clipboard.min.js"),
            Script("new ClipboardJS('.to_clipboard');"),
            Header(nav(label=ref["id"],
                       commands=[A(Tx("Update"), 
                                   href=f"/reference/{refid}?reload=yes"),
                                 A(Tx("Clipboard"),
                                   href="#",
                                   cls="to_clipboard", 
                                   data_clipboard_text=f'[@{ref["id"]}]')
                                 ]),
                   cls="container"),
            Main(Table(*rows),
                 Div(NotStr(ref.html)),
                 cls="container"))


if __name__ == "__main__":
    serve()
