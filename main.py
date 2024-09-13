"Web view and edit of Markdown book contents."

from icecream import ic

import copy
import os.path
import sys

from fasthtml.common import *
import bibtexparser
import yaml

import constants
import docx_creator
import pdf_creator
import utils

from book import Book

Tx = utils.Tx

if len(sys.argv) == 2:
    BOOK_DIRPATH = sys.argv[1]
    if not os.path.isabs(BOOK_DIRPATH):
        BOOK_DIRPATH = os.path.join(constants.TEXTS_DIRPATH, BOOK_DIRPATH)
else:
    BOOK_DIRPATH = os.getcwd()

# 'static_path' does not seem to do its job?
app, rt = fast_app(live=True, static_path=constants.SOURCE_DIRPATH)


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
        _book = Book(BOOK_DIRPATH)
        return _book

def get_references(reload=False):
    "Get the references book, cached."
    global _references
    if reload:
        try:
            del _references
        except NameError:
            pass
    try:
        return _references
    except NameError:
        _references = Book(constants.REFERENCES_DIRPATH)
        return _references


def nav(item=None, label=None, actions=None):
    "The standard navigation bar."
    NAV_STYLE = "outline-color: {color}; outline-width:8px; outline-style:solid; padding:0px 10px; border-radius:5px;"
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
             Li(A(Tx("References"), href="/references")),
             Li(A(Tx("Index"), href="/index"))]
    if actions:
        items.append(Li(Details(Summary(Tx("Actions")),
                                Ul(*[Li(c) for c in actions], dir="rtl"),
                                cls="dropdown")))
    entries.append(Ul(*items))
    return Nav(*entries, style=nav_style)

@rt("/")
def get():
    "Home page; list of sections and texts."
    book = get_book(reload=True)
    return (Title("mdbook"),
            Header(nav(actions=[A(f'{Tx("Create")} DOCX', href="/docx"),
                                A(f'{Tx("Create")} PDF', href="/pdf"),
                                A(f'{Tx("Create")} {Tx("archive")}', href="/archive"),
                                ]),
                   cls="container"),
            Main(toc(book.items), cls="container")
            )

def toc(items):
    "Recursive lists of sections and texts."
    parts = []
    for item in items:
        n_words = f"{utils.thousands(item.n_words)}"
        n_characters = f"{utils.thousands(len(item))}"
        length = f'{n_words} {Tx("words")}; {n_characters} {Tx("characters")}'
        if item.is_section:
            parts.append(Li(A(str(item),
                              style=f"color: {item.status.color};",
                              href=f"/section/{item.urlpath}"),
                            NotStr("&nbsp;&nbsp;&nbsp;"),
                            Small(length, style="color: silver;"),
                            style=f"color: {item.status.color};",))
            parts.append(toc(item.items))
        else:
            parts.append(Li(A(str(item),
                              style=f"color: {item.status.color};",
                              href=f"/text/{item.urlpath}"),
                            NotStr("&nbsp;&nbsp;&nbsp;"),
                            Small(length, style="color: silver;")))
    return Ol(*parts)

@rt("/text/{path:path}", methods=["get", "post"])
def view_text(path:str, content:str=None, status:str=None):
    "View the text, or edit and save."
    text = get_book()[path]
    text.read()
    if content is not None:
        text.write(content=content)
    if status is not None:
        text.status = status
        text.write()
    text.read()
    return (Title(text.title),
            Header(nav(text, actions=[A(Tx("Edit"), href=f"/edit/{path}")]),
                   cls="container"),
            Main(NotStr(text.html), cls="container")
            )

@rt("/edit/{path:path}")
def get(path:str):
    "Edit the text."
    text = get_book()[path]
    assert text.is_text
    text.read()
    status_options = []
    for status in constants.STATUSES:
        if text.status == status:
            status_options.append(Option(Tx(str(status)), selected=True, value=repr(status)))
        else:
            status_options.append(Option(Tx(str(status)), value=repr(status)))
    return (Title("mdbook"),
            Header(nav(label=f'{Tx("Edit")} {text.fullname}'), cls="container"),
            Main(Form(
                Textarea(NotStr(text.content), name="content", rows="30"),
                Fieldset(
                    Legend(Tx("Status"),
                           Select(*status_options, name="status", required=True))
                ),
                Button("Save"),
                action=f"/text/{path}",
                method="post"),
                 cls="container"),
            )

@rt("/section/{path:path}")
def get(path:str):
    "View the section."
    section = get_book()[path]
    assert section.is_section
    return (Title(section.title),
            Header(nav(section), cls="container"),
            Main(toc(section.items), cls="container")
            )

@rt("/title")
def get():
    "Title page."
    book = get_book()
    book.index.read()
    segments = [H1(book.title)]
    if book.subtitle:
        segments.append(H2(book.subtitle))
    for author in book.authors:
        segments.append(H3(author))
    segments.append(P(f'{utils.thousands(book.n_words)} {Tx("words")},'
                      f' {utils.thousands(len(book))} {Tx("characters")}.'))
    segments.append(NotStr(book.index.html))
    return (Title(Tx("Title")),
            Header(nav(label=Tx("Title"),
                       actions=[A(f'{Tx("Create")} DOCX', href="/docx"),
                                A(f'{Tx("Create")} PDF', href="/pdf"),
                                A(f'{Tx("Create")} {Tx("archive")}', href="/archive"),
                                ]),
                   cls="container"),
            Main(*segments, cls="container")
            )

@rt("/references")
def get():
    "List of references."
    references = get_references(reload=True)
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
            parts.extend(links)

        xrefs = []
        texts = get_book().references.get(ref["id"], [])
        for text in sorted(texts, key=lambda t: t.ordinal):
            if xrefs:
                xrefs.append(Br())
            xrefs.append(A(text.fullname,
                           cls="secondary",
                           href=f"/text/{text.fullname}"))
        if xrefs:
            parts.append(Small(Br(), *xrefs))
        items.append(P(*parts, id=ref["id"].replace(" ", "_")))

    return (Title(Tx("References")),
            Header(nav(label=Tx("References"),
                       actions=[A(Tx("Add BibTex"), href="/bibtex")]),
                   cls="container"),
            Main(*items, cls="container")
            )

@rt("/reference/{refid:str}")
def get(refid:str, reload:str=None):
    "Reference details."
    ref = get_references(reload)[refid.replace("_", " ")]
    rows = [Tr(Td(Tx("Identifier")),
               Td(Img(src="/clipboard.svg",
                     title="Refid to clipboard",
                     style="cursor: pointer;",
                     cls="to_clipboard", 
                     data_clipboard_text=f'[@{ref["id"]}]'),
                  NotStr("&nbsp;"),
                  f'[@{ref["id"]}]')),
            Tr(Td(Tx("Authors")), Td("; ".join(ref.get("authors") or [])))
            ]
    for key in ["year", "title", "type", "edition_published", "language", "date",
                "keywords", "journal", "volume", "number", "pages", "publisher"]:
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
            Header(nav(label=ref["id"],
                       actions=[A(Tx("Clipboard"),
                                  href="#",
                                  cls="to_clipboard", 
                                  data_clipboard_text=f'[@{ref["id"]}]'),
                                A(Tx("Reload"), 
                                  href=f"/reference/{refid}?reload=yes"),
                                ]),
                   cls="container"),
            Main(Table(*rows),
                 Div(NotStr(ref.html)),
                 cls="container"))

@rt("/bibtex", methods=["get", "post"])
def bibtex(data:str=None):
    "Add reference using BibTex data."
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
            get_references(reload=True)
            result.append(reference)
        return (Title("Added reference(s)"),
                Header(nav(label="Added reference(s)"), cls="container"),
                Main(Ul(
                    *[Li(A(r["id"], href=f'/reference/{r["id"]}')) for r in result]),
                     cls="container")
                )
    else:
        return (Title("Add reference"),
                Header(nav(label="Add reference"), cls="container"),
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

@rt("/index")
def get():
    "Page listing the indexed terms."
    items = []
    for key, texts in sorted(get_book().indexed.items(), key=lambda tu: tu[0].lower()):
        links = []
        for text in sorted(texts, key=lambda t: t.ordinal):
            if links:
                links.append(NotStr(",&nbsp; "))
            links.append(A(text.fullname, cls="secondary", href=f"/text/{text.fullname}"))
        items.append(Li(key, Br(), Small(*links)))
    return (Title(Tx("Index")),
            Header(nav(label=Tx("Index")), cls="container"),
            Main(Ul(*items), cls="container")
            )

@rt("/docx")
def get():
    "Get the parameters for outputting DOCX file."
    docx_settings = get_book().frontmatter.setdefault("docx", {})
    page_break_level = docx_settings.get("page_break_level", 1)
    page_break_options = []
    for value in range(0, 7):
        if value == page_break_level:
            page_break_options.append(Option(str(value), selected=True))
        else:
            page_break_options.append(Option(str(value)))
    footnotes_location = docx_settings.get("footnotes_location", constants.FOOTNOTES_EACH_TEXT)
    footnotes_options = []
    for value in constants.FOOTNOTES_LOCATIONS:
        if value == footnotes_location:
            footnotes_options.append(Option(Tx(value.capitalize()),
                                            value=value, selected=True))
        else:
            footnotes_options.append(Option(Tx(value.capitalize()), value=value))
    reference_font = docx_settings.get("reference_font", constants.NORMAL)
    reference_options = []
    for value in constants.FONT_STYLES:
        if value == reference_font:
            reference_options.append(Option(Tx(value.capitalize()),
                                            value=value, selected=True))
        else:
            reference_options.append(Option(Tx(value.capitalize())))
    indexed_font = docx_settings.get("indexed_font", constants.NORMAL)
    indexed_options = []
    for value in constants.FONT_STYLES:
        if value == indexed_font:
            indexed_options.append(Option(Tx(value.capitalize()), 
                                          value=value, selected=True))
        else:
            indexed_options.append(Option(Tx(value.capitalize()),
                                          value=value))
    return (Title(f'{Tx("Create")} DOCX'),
            Header(nav(label=f'{Tx("Create")} DOCX'), cls="container"),
            Main(Form(
                    Fieldset(
                    Legend(Tx("Page break level")),
                    Select(*page_break_options, name="page_break_level")
                ),
                Fieldset(
                    Legend(Tx("Footnotes location")),
                    Select(*footnotes_options, name="footnotes_location")
                ),
                Fieldset(
                    Legend(Tx("Reference font")),
                    Select(*reference_options, name="reference_font")
                ),
                Fieldset(
                    Legend(Tx("Indexed font")),
                    Select(*indexed_options, name="indexed_font")
                ),
                Button(f'{Tx("Create")} DOCX'),
                action="/docx_create",
                method="post"),
                 cls="container")
            )

@rt("/docx_create")
def post(page_break_level:int=None,
         footnotes_location:str=None,
         reference_font:str=None,
         indexed_font:str=None):
    book = get_book()
    original = copy.deepcopy(book.frontmatter)
    docx_settings = book.frontmatter.setdefault("docx", {})
    docx_settings["page_break_level"] = page_break_level
    docx_settings["footnotes_location"] = footnotes_location
    docx_settings["reference_font"] = reference_font
    docx_settings["indexed_font"] = indexed_font
    if book.frontmatter != original:
        book.index.write()
    filepath = os.path.join(BOOK_DIRPATH, book.title + ".docx")
    creator = docx_creator.Creator(book, get_references())
    creator.create(filepath)
    return (Title(f'{Tx("Created")} DOCX'),
            Header(nav(label=f'{Tx("Created")} DOCX'), cls="container"),
            Main(P(f'{Tx("File path")}: {filepath}'),
                 P(f'{Tx("Page break level")}: {page_break_level}'),
                 P(f'{Tx("Footnotes location")}: {Tx(footnotes_location.capitalize())}'),
                 P(f'{Tx("Reference font")}: {Tx(reference_font.capitalize())}'),
                 P(f'{Tx("Indexed font")}: {Tx(indexed_font.capitalize())}'),
                 cls="container")
            )

@rt("/pdf")
def get():
    pdf_settings = get_book().frontmatter.setdefault("pdf", {})
    page_break_level = pdf_settings.get("page_break_level", 1)
    page_break_options = []
    for value in range(0, 7):
        if value == page_break_level:
            page_break_options.append(Option(str(value), selected=True))
        else:
            page_break_options.append(Option(str(value)))
    contents_pages = pdf_settings.get("contents_pages", True)

    footnotes_location = pdf_settings.get("footnotes_location", constants.FOOTNOTES_EACH_TEXT)
    footnotes_options = []
    for value in constants.FOOTNOTES_LOCATIONS:
        if value == footnotes_location:
            footnotes_options.append(Option(Tx(value.capitalize()), value=value, selected=True))
        else:
            footnotes_options.append(Option(Tx(value.capitalize()), value=value))

    indexed_xref = pdf_settings.get("indexed_xref", constants.PDF_PAGE_NUMBER)
    indexed_options = []
    for value in constants.PDF_INDEXED_XREF_DISPLAY:
        if value == indexed_xref:
            indexed_options.append(Option(Tx(value.capitalize()), value=value, selected=True))
        else:
            indexed_options.append(Option(Tx(value.capitalize()), value=value))

    return (Title(f'{Tx("Create")} PDF'),
            Header(nav(label=f'{Tx("Create")} PDF'), cls="container"),
            Main(Form(
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
                    Legend(Tx("Footnotes location")),
                    Select(*footnotes_options, name="footnotes_location")
                ),
                Fieldset(
                    Legend(Tx("Display of indexed term reference")),
                    Select(*indexed_options, name="indexed_xref")
                ),
                Button(f'{Tx("Create")} PDF'),
                action="/pdf_create",
                method="post"),
                 cls="container")
            )

@rt("/pdf_create")
def post(page_break_level:int=None,
         contents_pages:bool=False,
         footnotes_location:str=None,
         indexed_xref:str=None):
    book = get_book()
    original = copy.deepcopy(book.frontmatter)
    pdf_settings = book.frontmatter.setdefault("pdf", {})
    pdf_settings["page_break_level"] = page_break_level
    pdf_settings["footnotes_location"] = footnotes_location
    pdf_settings["indexed_xref"] = indexed_xref
    if book.frontmatter != original:
        book.index.write()
    filepath = os.path.join(BOOK_DIRPATH, book.title + ".pdf")
    creator = pdf_creator.Creator(book, get_references())
    creator.create(filepath)
    return (Title(f'{Tx("Created")} PDF'),
            Header(nav(label=f'{Tx("Created")} PDF'), cls="container"),
            Main(P(f'{Tx("File path")}: {filepath}'),
                 P(f'{Tx("Page break level")}: {page_break_level}'),
                 P(f'{Tx("Contents pages")}: {Tx(str(contents_pages))}'),
                 P(f'{Tx("Footnotes location")}: {Tx(footnotes_location.capitalize())}'),
                 P(f'{Tx("Indexed reference display")}: {Tx(indexed_xref.capitalize())}'),
                 cls="container")
            )

@rt("/archive")
def get():
    "Create an archive file of the book."
    filepath, number = get_book().archive()
    return (Title(f'{Tx("Created")} {Tx("archive")}'),
            Header(nav(label=f'{Tx("Created")} {Tx("archive")}'), cls="container"),
            Main(P(f'{Tx("File path")}: {filepath}'),
                 P(f'{Tx("Number of files")}: {number}'),
                 cls="container")
            )


serve()
