"Web view and edit of Markdown books."

import io
from http import HTTPStatus
import os
import shutil
import string
import sys
import urllib

import fasthtml
from fasthtml.common import *
import bibtexparser
import marko
import psutil
import requests
import yaml

import components
import constants
import docx_creator
import pdf_creator
import utils
from utils import Tx

from book import Book


def error(message, status_code):
    return Response(content=str(message), status_code=status_code)


login_redir = RedirectResponse("/login", status_code=HTTPStatus.SEE_OTHER)


def before(req, sess):
    "Login session handling."
    if "apikey" in req.headers and "MDBOOK_APIKEY" in os.environ:
        if req.headers["apikey"] == os.environ["MDBOOK_APIKEY"]:
            auth = req.scope["auth"] = os.environ["MDBOOK_USER"]
        else:
            return error("invalid apikey", HTTPStatus.FORBIDDEN)
    else:
        auth = req.scope["auth"] = sess.get("auth", None)
    if not auth:
        return login_redir


beforeware = Beforeware(
    before,
    skip=[r"/favicon\.ico", r".*\.css", r".*\.js", r".*\.svg", "/login"],
)

app, rt = fast_app(
    live="MDBOOK_DEVELOPMENT" in os.environ,
    static_path="static",
    before=beforeware,
    hdrs=(Link(rel="stylesheet", href="/mods.css", type="text/css"),),
)


@rt("/")
def get(auth):
    "Home page; list of books."

    # Check that site is properly configured.
    for envvar in ["MDBOOK_DIR", "MDBOOK_USER", "MDBOOK_PASSWORD"]:
        if os.environ.get(envvar) is None:
            return error(
                f"environment variable {envvar} has not been defined",
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    books = []
    for bid in os.listdir(os.environ["MDBOOK_DIR"]):
        dirpath = os.path.join(os.environ["MDBOOK_DIR"], bid)
        if not os.path.isdir(dirpath):
            continue
        if bid == constants.REFERENCES:
            continue
        try:
            book = Book(dirpath, index_only=True)
            if not book.allow_read(auth):
                continue
            books.append(book)
        except FileNotFoundError:
            pass
    books.sort(key=lambda b: b.modified, reverse=True)
    hrows = Tr(
        Th(Tx("Title")),
        Th(Tx("Type")),
        Th(Tx("Status")),
        Th(Tx("Characters")),
        Th(Tx("Owner")),
        Th(Tx("Modified")),
    )
    rows = []
    for book in books:
        rows.append(
            Tr(
                Td(A(book.title, href=f"/book/{book.name}")),
                Td(Tx(book.frontmatter["type"].capitalize())),
                Td(Tx(book.frontmatter["status"].capitalize())),
                Td(Tx(utils.thousands(book.frontmatter["sum_characters"]))),
                Td(book.frontmatter["owner"]),
                Td(book.modified),
            )
        )
    actions = [
        A(f'{Tx("Create")} {Tx("book")}', href="/book"),
        A(f'{Tx("Download")} TGZ', href="/tgz"),
    ]
    if "MDBOOK_UPDATE_SITE" in os.environ:
        actions.append(A(Tx("Update"), href="/update"))

    return (
        Title(Tx("Books")),
        components.header(title=Tx("Books"), actions=actions, state_url="/state"),
        Main(Table(Thead(*hrows), Tbody(*rows)), cls="container"),
    )


@rt("/references")
def get(auth):
    "Page for list of references."
    references = utils.get_references(refresh=True)
    references.write()  # Updates the 'index.md' file, if necessary.
    items = []
    for ref in references.items:
        parts = [
            Img(
                src="/clipboard.svg",
                title="Refid to clipboard",
                style="cursor: pointer;",
                cls="to_clipboard",
                data_clipboard_text=f'[@{ref["name"]}]',
            ),
            NotStr("&nbsp;"),
            A(
                Strong(ref["name"], style="color: royalblue;"),
                href=f'/reference/{ref["id"]}',
            ),
            NotStr("&nbsp;&nbsp;"),
        ]
        if ref.get("authors"):
            authors = [utils.short_name(a) for a in ref["authors"]]
            if len(authors) > 5:
                authors = authors[:5] + ["..."]
            parts.append(", ".join(authors))
        if ref.get("title"):
            parts.append(Br())
            parts.append(ref["title"])

        links = []
        if ref.get("type") == "article":
            parts.append(Br())
            parts.append(I(ref["journal"]))
            if ref.get("volume"):
                parts.append(f' {ref["volume"]}')
            if ref.get("number"):
                parts.append(f' ({ref["number"]})')
            if ref.get("pages"):
                parts.append(f' {ref["pages"].replace("--", "-")}')
            if ref.get("year"):
                parts.append(f' ({ref["year"]})')
            if ref.get("edition_published"):
                parts.append(f' [{ref["edition_published"]}]')
        elif ref.get("type") == "book":
            parts.append(Br())
            if ref.get("publisher"):
                parts.append(f'{ref["publisher"]}')
                if ref.get("edition_published"):
                    parts.append(f' {ref["edition_published"]}')
                    if ref.get("year"):
                        parts.append(f' [{ref["year"]}]')
                elif ref.get("year"):
                    parts.append(f' {ref["year"]}')
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
                parts.append(f' (Accessed: {ref["accessed"]})')
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
        # texts = utils.get_book().references.get(ref["name"], [])
        # for text in sorted(texts, key=lambda t: t.ordinal):
        #     if xrefs:
        #         xrefs.append(Br())
        #     xrefs.append(A(text.fulltitle,
        #                    cls="secondary",
        #                    href=f"/book/XXX/{text.fulltitle}"))
        # if xrefs:
        #     parts.append(Small(Br(), *xrefs))
        items.append(P(*parts, id=ref["name"]))

    title = f'{Tx("References")} ({len(references.items)})'
    actions = [
        A(Tx("Add BibTex"), href="/bibtex"),
        A(f'{Tx("Download")} {Tx("references")} TGZ', href="/references/tgz"),
        A(f'{Tx("Upload")} {Tx("references")} TGZ', href="/references/upload"),
    ]
    if "MDBOOK_UPDATE_SITE" in os.environ:
        actions.append(A(Tx("Update"), href="/update/references"))

    return (
        Title(title),
        components.header(
            title=title,
            actions=actions,
            state_url="/state/references",
        ),
        Main(*items, cls="container"),
    )


@rt("/references/tgz")
def get(auth):
    "Download a gzipped tar file of all references."
    book = utils.get_references(refresh=True)
    output = book.get_tgzfile()
    filename = f"mdbook_references_{utils.timestr(safe=True)}.tgz"

    return Response(
        content=output.getvalue(),
        media_type=constants.GZIP_MIMETYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@rt("/references/upload")
def get(auth):
    "Upload a gzipped tar file of references; replace any with the same name."
    title = f'{Tx("Upload")} {Tx("references")}'
    return (
        Title(title),
        components.header(title=title),
        Main(
            Form(
                Fieldset(
                    Legend(Tx(f'{Tx("Upload")} TGZ')),
                    Input(type="file", name="tgzfile"),
                ),
                Button(Tx("Upload")),
                action="/references/upload",
                method="post",
            ),
            cls="container",
        ),
    )


@rt("/references/upload")
async def post(auth, tgzfile: UploadFile):
    "Actually add or replace references by contents of the uploaded file."
    content = await tgzfile.read()
    if not content:
        return error("empty TGZ file", HTTPStatus.BAD_REQUEST)
    try:
        utils.unpack_tgzfile(
            os.path.join(os.environ["MDBOOK_DIR"], constants.REFERENCES),
            content,
            references=True,
        )
    except ValueError as message:
        return error(f"error reading TGZ file: {message}", HTTPStatus.BAD_REQUEST)

    return RedirectResponse("/references", status_code=HTTPStatus.SEE_OTHER)


@rt("/reference/{refid:str}")
def get(auth, refid: str):
    "Page for details of a reference."
    try:
        ref = utils.get_references()[refid.replace("_", " ")]
    except KeyError:
        return error("no such reference", HTTPStatus.NOT_FOUND)
    rows = [
        Tr(
            Td(Tx("Reference")),
            Td(
                f'{ref["name"]}',
                NotStr("&nbsp;"),
                Img(
                    src="/clipboard.svg",
                    title=Tx("Reference to clipboard"),
                    style="cursor: pointer;",
                    cls="to_clipboard",
                    data_clipboard_text=f'[@{ref["name"]}]',
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
        components.header(
            title=ref["name"],
            actions=[
                A(
                    Tx("Clipboard"),
                    href="#",
                    cls="to_clipboard",
                    data_clipboard_text=f'[@{ref["name"]}]',
                ),
            ],
        ),
        Main(Table(*rows), Div(NotStr(ref.html)), cls="container"),
    )


@rt("/bibtex")
def get(auth):
    "Page for adding reference(s) using BibTex data."
    return (
        Title("Add reference"),
        components.header(title="Add reference"),
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
def post(auth, data: str):
    "Actually add reference(s) using BibTex data."
    result = []
    for entry in bibtexparser.loads(data).entries:
        authors = utils.cleanup_latex(entry["author"])
        authors = [a.strip() for a in authors.split(" and ")]
        year = entry["year"].strip()
        name = authors[0].split(",")[0].strip()
        for char in [""] + list(string.ascii_lowercase):
            name = f"{name} {year}{char}"
            id = utils.nameify(name)
            if utils.get_references().get(id) is None:
                break
        else:
            raise ValueError(f"could not form unique id for {name} {year}")
        new = dict(
            id=id, name=name, type=entry["ENTRYTYPE"], authors=authors, year=year
        )
        for key, value in entry.items():
            if key in ("author", "ID", "ENTRYTYPE"):
                continue
            value = utils.cleanup_latex(value).strip()
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
            parts = month.split("~")
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
        reference = utils.get_references().create_text(new["name"])
        for key, value in new.items():
            reference[key] = value
        if abstract:
            reference.write("**Abstract**\n\n" + abstract)
        else:
            reference.write()
        references = utils.get_references()
        references.read()
        references.items.sort(key=lambda r: r["id"].lower())
        references.write()
        result.append(reference)

    return (
        Title("Added reference(s)"),
        components.header(title="Added reference(s)"),
        Main(
            Ul(*[Li(A(r["name"], href=f'/reference/{r["id"]}')) for r in result]),
            cls="container",
        ),
    )


@rt("/book")
def get(auth):
    "Page to create and/or upload book using a gzipped tar file."
    title = f'{Tx("Create or upload")} {Tx("book")}'
    return (
        Title(title),
        components.header(title=title),
        Main(
            Form(
                Fieldset(
                    Legend(Tx("Title")),
                    Input(type="text", name="title", required=True, autofocus=True),
                ),
                Fieldset(
                    Legend(Tx(f'{Tx("Upload")} TGZ')),
                    Input(type="file", name="tgzfile"),
                ),
                Button(Tx("Create or upload")),
                action="/book",
                method="post",
            ),
            cls="container",
        ),
    )


@rt("/book")
async def post(auth, title: str, tgzfile: UploadFile):
    "Actually create and/or upload book using a gzipped tar file."
    if not title:
        return error("book title may not be empty", HTTPStatus.BAD_REQUEST)
    if title.startswith("_"):
        return error(
            "book title may not start with an underscore '_'", HTTPStatus.BAD_REQUEST
        )
    bid = utils.nameify(title)
    if not bid:
        return error("book bid may not be empty", HTTPStatus.BAD_REQUEST)
    dirpath = os.path.join(os.environ["MDBOOK_DIR"], bid)
    if os.path.exists(dirpath):
        return error(f"book {bid} already exists", HTTPStatus.CONFLICT)
    content = await tgzfile.read()
    if content:
        try:
            utils.unpack_tgzfile(dirpath, content)
        except ValueError as message:
            return error(f"error reading TGZ file: {message}", HTTPStatus.BAD_REQUEST)
    # Just create the directory; no content.
    else:
        os.mkdir(dirpath)
    book = Book(dirpath)
    book.frontmatter["title"] = title or book.title
    book.frontmatter["owner"] = auth
    book.write()

    return RedirectResponse(f"/book/{book.name}", status_code=HTTPStatus.SEE_OTHER)


@rt("/book/{bid:str}")
def get(auth, bid: str):
    "Book page; list of sections and texts."
    if not bid:
        return error("no book name provided", HTTPStatus.BAD_REQUEST)
    try:
        book = utils.get_book(bid, refresh=True)
    except KeyError as message:
        return error(message, HTTPStatus.NOT_FOUND)
    book.write()  # Updates the 'index.md' file, if necessary.
    actions = [
        A(f'{Tx("Edit")}', href=f"/edit/{bid}"),
        A(f'{Tx("Create")} {Tx("section")}', href=f"/section/{bid}"),
        A(f'{Tx("Create")} {Tx("text")}', href=f"/text/{bid}"),
        A(f'{Tx("Download")} DOCX', href=f"/docx/{bid}"),
        A(f'{Tx("Download")} PDF', href=f"/pdf/{bid}"),
        A(f'{Tx("Download")} TGZ', href=f"/tgz/{bid}"),
        A(f'{Tx("Update")}', href=f"/update/{bid}"),
        A(f'{Tx("Delete")}', href=f"/delete/{bid}"),
    ]
    if len(book.items) == 0:
        content = H3(A(Tx("Article"), href=f"/title/{bid}"))
    else:
        content = components.toc(book, book.items, show_arrows=True)

    return (
        Title(book.title),
        components.header(book=book, actions=actions, state_url=f"/state/{bid}"),
        Main(content, cls="container"),
        components.footer(book),
    )


@rt("/book/{bid:str}/{path:path}")
def get(auth, bid: str, path: str):
    "View the book text or section."
    if not bid:
        return error("no book id provided", HTTPStatus.BAD_REQUEST)
    book = utils.get_book(bid)
    item = book[path]
    actions = [A(Tx("Edit"), href=f"/edit/{bid}/{path}")]
    if item.is_text:
        item.read()
        actions.append(A(Tx("Convert to section"), href=f"/to_section/{bid}/{path}"))
        actions.append(A(f'{Tx("Download")} DOCX', href=f"/docx/{bid}/{path}"))
        actions.append(A(f'{Tx("Delete")}', href=f"/delete/{bid}/{path}"))
        segments = []
    elif item.is_section:
        actions.append(
            A(f'{Tx("Create")} {Tx("section")}', href=f"/section/{bid}/{path}")
        )
        actions.append(A(f'{Tx("Create")} {Tx("text")}', href=f"/text/{bid}/{path}"))
        actions.append(A(f'{Tx("Download")} DOCX', href=f"/docx/{bid}/{path}"))
        if len(item.items) == 0:
            actions.append(A(f'{Tx("Delete")}', href=f"/delete/{bid}/{path}"))
        segments = [components.toc(book, item.items)]

    return (
        Title(item.title),
        components.header(book=book, item=item, actions=actions),
        Main(
            H3(item.heading),
            *segments,
            NotStr(item.html),
            cls="container",
        ),
        components.footer(item),
    )


@rt("/edit/{bid:str}")
def get(auth, bid: str):
    "Page for editing the book data."
    if not bid:
        return error("no book id provided", HTTPStatus.BAD_REQUEST)
    book = utils.get_book(bid)
    fields = [
        Fieldset(
            Legend(Tx("Title")),
            Input(
                name="title", value=book.frontmatter.get("title", ""), autofocus=True
            ),
        ),
        Fieldset(
            Legend(Tx("Subtitle")),
            Input(name="subtitle", value=book.frontmatter.get("subtitle", "")),
        ),
        Fieldset(
            Legend(Tx("Authors")),
            Textarea(
                "\n".join(book.frontmatter.get("authors", [])), name="authors", rows="3"
            ),
        ),
    ]
    if len(book.items) == 0:
        status_options = []
        for status in constants.STATUSES:
            if book.status == status:
                status_options.append(
                    Option(Tx(str(status)), selected=True, value=repr(status))
                )
            else:
                status_options.append(Option(Tx(str(status)), value=repr(status)))
        fields.append(
            Fieldset(
                Legend(Tx("Status")),
                Select(*status_options, name="status", required=True),
            )
        )
    language_options = []
    for language in constants.LANGUAGE_CODES:
        if book.frontmatter.get("language") == language:
            language_options.append(Option(language, selected=True))
        else:
            language_options.append(Option(language))
    fields.append(
        Fieldset(Legend(Tx("Language")), Select(*language_options, name="language"))
    )
    fields.append(
        Fieldset(
            Legend(Tx("Text")),
            Textarea(
                NotStr(book.content),
                name="content",
                rows="10",
            ),
        )
    )

    return (
        Title(f'{Tx("Edit")} {book.title}'),
        components.header(book=book, title=f'{Tx("Edit")} {book.title}'),
        Main(
            Form(*fields, Button(Tx("Save")), action=f"/edit/{bid}", method="post"),
            cls="container",
        ),
    )


@rt("/edit/{bid:str}")
def post(
    auth,
    bid: str,
    title: str,
    subtitle: str,
    authors: str,
    content: str,
    status: str = None,
    language: str = None,
):
    "Actually edit the book data."
    if not bid:
        return error("no book id provided", HTTPStatus.BAD_REQUEST)
    book = utils.get_book(bid)
    book.frontmatter["title"] = title
    book.frontmatter["subtitle"] = subtitle
    book.frontmatter["authors"] = [a.strip() for a in authors.split("\n")]
    if status:
        book.frontmatter["status"] = status
    else:
        book.frontmatter.pop("status", None)
    if language:
        book.frontmatter["language"] = language
    else:
        book.frontmatter.pop("language", None)
    book.write(content=content, force=True)

    return RedirectResponse(f"/title/{bid}", status_code=HTTPStatus.SEE_OTHER)


@rt("/edit/{bid:str}/{path:path}")
def get(auth, bid: str, path: str):
    "Page for editing the item (section or text)."
    if not bid:
        return error("no book id provided", HTTPStatus.BAD_REQUEST)
    book = utils.get_book(bid)
    item = book[path]
    title_field = Fieldset(
        Label(Tx("Title")),
        Input(name="title", value=item.title, required=True, autofocus=True),
    )
    if item.is_text:
        item.read()
        status_options = []
        for status in constants.STATUSES:
            if item.status == status:
                status_options.append(
                    Option(Tx(str(status)), selected=True, value=repr(status))
                )
            else:
                status_options.append(Option(Tx(str(status)), value=repr(status)))
        fields = [
            Div(
                title_field,
                Fieldset(
                    Legend(Tx("Status")),
                    Select(*status_options, name="status", required=True),
                ),
                cls="grid",
            )
        ]
    elif item.is_section:
        fields = [title_field]
    fields.append(
        Fieldset(
            Legend(Tx("Text")),
            Textarea(NotStr(item.content), name="content", rows="30"),
        )
    )
    fields.append(Button("Save"))

    return (
        Title(f'{Tx("Edit")} {item.fulltitle}'),
        components.header(book=book, title=f'{Tx("Edit")} {item.fulltitle}'),
        Main(
            Form(*fields, action=f"/edit/{bid}/{path}", method="post"),
            cls="container",
        ),
    )


@rt("/edit/{bid:str}/{path:path}")
def post(auth, bid: str, path: str, title: str, content: str, status: str = None):
    "Actually edit the item (section or text)."
    if not bid:
        return error("no book id provided", HTTPStatus.BAD_REQUEST)
    book = utils.get_book(bid)
    item = book[path]
    item.title = title
    item.name = title  # Changes name of directory/file.
    if item.is_text:
        if status is not None:
            item.status = status
    item.write(content=content)
    book.write()

    return RedirectResponse(
        f"/book/{bid}/{item.path}", status_code=HTTPStatus.SEE_OTHER
    )


@rt("/up/{bid:str}/{path:path}")
def get(auth, bid: str, path: str):
    "Move item up in its sibling list."
    if not bid:
        return error("no book id provided", HTTPStatus.BAD_REQUEST)
    book = utils.get_book(bid)
    book[path].up()
    book.write()

    return RedirectResponse(f"/book/{bid}", status_code=HTTPStatus.SEE_OTHER)


@rt("/down/{bid:str}/{path:path}")
def get(auth, bid: str, path: str):
    "Move item down in its sibling list."
    if not bid:
        return error("no book id provided", HTTPStatus.BAD_REQUEST)
    book = utils.get_book(bid)
    book[path].down()
    book.write()

    return RedirectResponse(f"/book/{bid}", status_code=HTTPStatus.SEE_OTHER)


@rt("/delete/{bid:str}")
def get(auth, bid: str):
    "Confirm delete of book."
    if not bid:
        return error("no book id provided", HTTPStatus.BAD_REQUEST)
    book = utils.get_book(bid)
    if len(book.items) != 0:
        return error("cannot delete non-empty book", HTTPStatus.CONFLICT)

    return (
        Title(book.title),
        components.header(book=book, title=book.title),
        Main(
            H3(Tx("Delete"), "?"),
            P(Mark(components.metadata(book))),
            Form(Button(Tx("Confirm")), action=f"/delete/{bid}", method="post"),
            cls="container",
        ),
    )


@rt("/delete/{bid:str}")
def post(auth, bid: str):
    "Delete the book."
    if not bid:
        return error("no book id provided", HTTPStatus.BAD_REQUEST)
    book = utils.get_book(bid)
    if len(book.items) != 0:
        return error("cannot delete non-empty book", HTTPStatus.CONFLICT)
    utils.delete_book(book)

    return RedirectResponse("/", status_code=HTTPStatus.SEE_OTHER)


@rt("/delete/{bid:str}/{path:path}")
def get(auth, bid: str, path: str):
    "Confirm delete of the text or section; section must be empty."
    if not bid:
        return error("no book id provided", HTTPStatus.BAD_REQUEST)
    book = utils.get_book(bid)
    item = book[path]
    if item.is_section and len(item.items) != 0:
        return error("cannot delete non-empty section", HTTPStatus.CONFLICT)

    return (
        Title(item.title),
        components.header(book=book, item=item, title=item.title),
        Main(
            H3(Tx("Delete"), "?"),
            Form(Button(Tx("Confirm")), action=f"/delete/{bid}/{path}", method="post"),
            cls="container",
        ),
    )


@rt("/delete/{bid:str}/{path:path}")
def post(auth, bid: str, path: str):
    "Delete the text or section; section must be empty."
    if not bid:
        return error("no book id provided", HTTPStatus.BAD_REQUEST)
    book = utils.get_book(bid)
    item = book[path]
    try:
        book.delete(item)
    except ValueError as message:
        return error(message, HTTPStatus.CONFLICT)

    return RedirectResponse(f"/book/{bid}", status_code=HTTPStatus.SEE_OTHER)


@rt("/to_section/{bid:str}/{path:path}")
def get(auth, bid: str, path: str):
    "Convert to section containing a text with this text."
    if not bid:
        return error("no book id provided", HTTPStatus.BAD_REQUEST)
    book = utils.get_book(bid)
    text = book[path]
    assert text.is_text

    return (
        Title(Tx("Convert to section")),
        components.header(book=book, title=Tx("Convert to section")),
        Main(
            P(Tx("Text"), ": ", text.fulltitle),
            Form(
                Button(Tx("Convert")), action=f"/to_section/{bid}/{path}", method="post"
            ),
            cls="container",
        ),
    )


@rt("/to_section/{bid:str}/{path:path}")
def post(auth, bid: str, path: str):
    "Convert to section containing a text with this text."
    if not bid:
        return error("no book id provided", HTTPStatus.BAD_REQUEST)
    book = utils.get_book(bid)
    text = book[path]
    assert text.is_text
    section = text.to_section()
    book.write()
    assert section.is_section

    return RedirectResponse(
        f"/book/{bid}/{section.path}", status_code=HTTPStatus.SEE_OTHER
    )


@rt("/text/{bid:str}/{path:path}")
def get(auth, bid: str, path: str):
    "Create a new text in the section."
    if not bid:
        return error("no book id provided", HTTPStatus.BAD_REQUEST)
    book = utils.get_book(bid)
    assert path == "" or book[path].is_section
    title = f'{Tx("Create")} {Tx("text")}'

    return (
        Title(title),
        components.header(book=book, title=title),
        Main(
            Form(
                Fieldset(
                    Label(Tx("Title")),
                    Input(name="title", required=True, autofocus=True),
                ),
                Button(Tx("Create")),
                action=f"/text/{bid}/{path}",
                method="post",
            ),
            cls="container",
        ),
    )


@rt("/text/{bid:str}/{path:path}")
def post(auth, bid: str, path: str, title: str = None):
    "Create a new text in the section."
    if not bid:
        return error("no book id provided", HTTPStatus.BAD_REQUEST)
    book = utils.get_book(bid)
    if path == "":
        parent = None
    else:
        parent = book[path]
        assert parent.is_section
    new = book.create_text(title, parent=parent)
    book.write()

    return RedirectResponse(f"/edit/{bid}/{new.path}", status_code=HTTPStatus.SEE_OTHER)


@rt("/section/{bid:str}/{path:path}")
def get(auth, bid: str, path: str):
    "Create a new section in the section."
    if not bid:
        return error("no book id provided", HTTPStatus.BAD_REQUEST)
    book = utils.get_book(bid)
    assert path == "" or book[path].is_section
    title = f'{Tx("Create")} {Tx("section")}'

    return (
        Title(title),
        components.header(book=book, title=title),
        Main(
            Form(
                Fieldset(
                    Label(Tx("Title")),
                    Input(name="title", required=True, autofocus=True),
                ),
                Button(Tx("Create")),
                action=f"/section/{bid}/{path}",
                method="post",
            ),
            cls="container",
        ),
    )


@rt("/section/{bid:str}/{path:path}")
def post(auth, bid: str, path: str, title: str = None):
    "Create a new section in the section."
    if not bid:
        return error("no book id provided", HTTPStatus.BAD_REQUEST)
    book = utils.get_book(bid)
    if path == "":
        parent = None
    else:
        parent = book[path]
        assert parent.is_section
    new = book.create_section(title, parent=parent)
    book.write()

    return RedirectResponse(f"/edit/{bid}/{new.path}", status_code=HTTPStatus.SEE_OTHER)


@rt("/title/{bid:str}")
def get(auth, bid: str):
    "Title page."
    if not bid:
        return error("no book id provided", HTTPStatus.BAD_REQUEST)
    book = utils.get_book(bid)
    segments = [H1(book.title)]
    if book.subtitle:
        segments.append(H2(book.subtitle))
    for author in book.authors:
        segments.append(H3(author))
    segments.append(NotStr(book.html))

    return (
        Title(Tx("Title")),
        components.header(
            book=book,
            title=Tx("Title"),
            actions=[
                A(f'{Tx("Edit")}', href=f"/edit/{bid}"),
                A(f'{Tx("Download")} DOCX', href=f"/docx/{bid}"),
                A(f'{Tx("Download")} PDF', href=f"/pdf/{bid}"),
                A(f'{Tx("Download")} TGZ', href=f"/tgz/{bid}"),
            ],
        ),
        Main(*segments, cls="container"),
    )


@rt("/index/{bid:str}")
def get(auth, bid: str):
    "Page listing the indexed terms."
    if not bid:
        return error("no book id provided", HTTPStatus.BAD_REQUEST)
    book = utils.get_book(bid)
    items = []
    for key, texts in sorted(book.indexed.items(), key=lambda tu: tu[0].lower()):
        refs = []
        for text in sorted(texts, key=lambda t: t.ordinal):
            refs.append(
                Li(A(text.fulltitle, cls="secondary", href=f"/book/{bid}/{text.path}"))
            )
        items.append(Li(key, Small(Ul(*refs))))

    return (
        Title(Tx("Index")),
        components.header(book=book, title=Tx("Index")),
        Main(Ul(*items), cls="container"),
    )


@rt("/statuslist/{bid:str}")
def get(auth, bid: str):
    "Page listing each status and texts in it."
    if not bid:
        return error("no book id provided", HTTPStatus.BAD_REQUEST)
    book = utils.get_book(bid)
    rows = [Tr(Th(Tx("Status"), Th(Tx("Texts"))))]
    for status in constants.STATUSES:
        texts = []
        for t in book.all_texts:
            if t.status == status:
                if texts:
                    texts.append(Br())
                texts.append(A(t.heading, href=f"/book/{bid}/{t.path}"))
        rows.append(Tr(Td(Tx(str(status)), valign="top"), Td(*texts)))

    return (
        Title(Tx("Status list")),
        components.header(book=book, title=Tx("Status list")),
        Main(Table(*rows), cls="container"),
    )


@rt("/docx/{bid:str}")
def get(auth, bid: str):
    "Download the DOCX for the whole book."
    if not bid:
        return error("no book id provided", HTTPStatus.BAD_REQUEST)
    return get_docx(bid)


@rt("/docx/{bid:str}/{path:path}")
def get(auth, bid: str, path: str):
    "Download the DOCX for a section or text in the book."
    if not bid:
        return error("no book id provided", HTTPStatus.BAD_REQUEST)
    return get_docx(bid, path)


def get_docx(bid, path=None):
    "Get the parameters for downloading the DOCX file."
    book = utils.get_book(bid)
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
                    Tx("Display"),
                ),
            )
        )
    else:
        fields.append(Hidden(name="path", value=item.path))
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
        components.header(book=book, title=f'{Tx("Download")} DOCX: {title}'),
        Main(Form(*fields, action=f"/docx/{bid}", method="post"), cls="container"),
    )


@rt("/docx/{bid:str}")
def post(
    auth,
    bid: str,
    path: str = None,
    title_page_metadata: bool = False,
    page_break_level: int = None,
    footnotes_location: str = None,
    reference_font: str = None,
    indexed_font: str = None,
):
    "Actually download the DOCX file of the book."
    if not bid:
        return error("no book id provided", HTTPStatus.BAD_REQUEST)
    book = utils.get_book(bid)
    if path:
        path = urllib.parse.unquote(path)
        item = book[path]
    else:
        item = None
    settings = book.frontmatter.setdefault("docx", {})
    settings["title_page_metadata"] = title_page_metadata
    settings["page_break_level"] = page_break_level
    settings["footnotes_location"] = footnotes_location
    settings["reference_font"] = reference_font
    settings["indexed_font"] = indexed_font
    if item is None:
        book.write()
        filename = book.title + ".docx"
    else:
        filename = item.title + ".docx"
    creator = docx_creator.Creator(book, utils.get_references(), item=item)
    output = creator.create()

    return Response(
        content=output.getvalue(),
        media_type=constants.DOCX_MIMETYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@rt("/pdf/{bid:str}")
def pdf(auth, bid: str):
    "Get the parameters for downloading PDF file of the whole book."
    if not bid:
        return error("no book id provided", HTTPStatus.BAD_REQUEST)
    book = utils.get_book(bid)
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
        components.header(book=book, title=f'{Tx("Download")} PDF'),
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
                        Tx("Display"),
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
                action=f"/pdf/{bid}",
                method="post",
            ),
            cls="container",
        ),
    )


@rt("/pdf/{bid:str}")
def post(
    auth,
    bid: str,
    title_page_metadata: bool = False,
    page_break_level: int = None,
    contents_pages: bool = False,
    contents_level: int = None,
    footnotes_location: str = None,
    indexed_xref: str = None,
):
    "Actually download the PDF file of the book."
    if not bid:
        return error("no book id provided", HTTPStatus.BAD_REQUEST)
    book = utils.get_book(bid)
    settings = book.frontmatter.setdefault("pdf", {})
    settings["title_page_metadata"] = title_page_metadata
    settings["page_break_level"] = page_break_level
    settings["contents_pages"] = contents_pages
    settings["contents_level"] = contents_level
    settings["footnotes_location"] = footnotes_location
    settings["indexed_xref"] = indexed_xref
    book.write()
    filename = book.title + ".pdf"
    creator = pdf_creator.Creator(book, utils.get_references())
    output = creator.create()

    return Response(
        content=output.getvalue(),
        media_type=constants.PDF_MIMETYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@rt("/tgz/{bid:str}")
def get(auth, bid: str):
    "Download a gzipped tar file of the book."
    if not bid:
        return error("no book id provided", HTTPStatus.BAD_REQUEST)
    book = utils.get_book(bid, refresh=True)
    filename = f"mdbook_{book.name}_{utils.timestr(safe=True)}.tgz"
    output = book.get_tgzfile()

    return Response(
        content=output.getvalue(),
        media_type=constants.GZIP_MIMETYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@rt("/state/{bid:str}")
def get(auth, bid: str):
    "Return JSON for complete state of this book."
    if not bid:
        return error("no book id provided", HTTPStatus.BAD_REQUEST)
    try:
        book = utils.get_book(bid, refresh=True)
    except KeyError as message:
        if bid == constants.REFERENCES:
            book = utils.get_references()
        else:
            return error(message, HTTPStatus.NOT_FOUND)
    result = dict(
        software="mdbook",
        version=constants.__version__,
        now=utils.timestr(localtime=False, display=False),
    )
    result.update(book.state)

    return result


@rt("/information")
def get(auth):
    "Various metadata."
    return (
        Title(Tx("Information")),
        components.header(title=Tx("Information")),
        Main(
            Table(
                Tr(Td(Tx("User")), Td(auth, " ", A("logout", href="/logout"))),
                Tr(
                    Td(Tx("Memory usage")),
                    Td(utils.thousands(psutil.Process().memory_info().rss), " bytes"),
                ),
                Tr(
                    Td(A("mdbook", href="https://github.com/pekrau/mdbook")),
                    Td(constants.__version__),
                ),
                Tr(
                    Td(A("Python", href="https://www.python.org/")),
                    Td(
                        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
                    ),
                ),
                Tr(
                    Td(A("fastHTML", href="https://fastht.ml/")),
                    Td(fasthtml.__version__),
                ),
                Tr(
                    Td(A("Marko", href="https://marko-py.readthedocs.io/")),
                    Td(marko.__version__),
                ),
                Tr(
                    Td(
                        A(
                            "python-docx",
                            href="https://python-docx.readthedocs.io/en/latest/",
                        )
                    ),
                    Td(docx_creator.docx.__version__),
                ),
                Tr(
                    Td(A("fpdf2", href="https://py-pdf.github.io/fpdf2/")),
                    Td(pdf_creator.fpdf.__version__),
                ),
                Tr(
                    Td(A("PyYAML", href="https://pypi.org/project/PyYAML/")),
                    Td(yaml.__version__),
                ),
                Tr(
                    Td(
                        A("bibtexparser", href="https://pypi.org/project/bibtexparser/")
                    ),
                    Td(bibtexparser.__version__),
                ),
            ),
            cls="container",
        ),
    )


@rt("/login")
def get():
    "Login form."
    if not (os.environ.get("MDBOOK_USER") and os.environ.get("MDBOOK_PASSWORD")):
        return Titled(
            "Invalid setup",
            H3("Invalid setup"),
            P("Environment variables MDBOOK_USER and/or MDBOOK_PASSWORD not set."),
        )
    else:
        return Titled(
            "Login",
            Form(
                Input(id="user", placeholder=Tx("User")),
                Input(id="password", type="password", placeholder=Tx("Password")),
                Button(Tx("Login")),
                action="/login",
                method="post",
            ),
        )


@rt("/login")
def post(user: str, password: str, sess):
    "Actually login."
    if not user or not password:
        return login_redir
    if user != os.environ["MDBOOK_USER"] or password != os.environ["MDBOOK_PASSWORD"]:
        return error("invalid credentials", HTTPStatus.FORBIDDEN)
    sess["auth"] = user

    return RedirectResponse("/", status_code=HTTPStatus.SEE_OTHER)


@rt("/logout")
def get(sess):
    del sess["auth"]
    return login_redir


@rt("/tgz")
def get(auth):
    "Download a gzipped tar file of all books."
    filename = f"mdbook_{utils.timestr(safe=True)}.tgz"
    return Response(
        content=utils.get_tgzfile(os.environ["MDBOOK_DIR"]).getvalue(),
        media_type=constants.GZIP_MIMETYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@rt("/state")
def get(auth):
    "Return JSON for the overall state of this site."
    return get_state()


def get_state():
    "Return JSON for the overall state of this site."
    books = {}
    for name in os.listdir(os.environ["MDBOOK_DIR"]):
        dirpath = os.path.join(os.environ["MDBOOK_DIR"], name)
        if not os.path.isdir(dirpath):
            continue
        book = Book(dirpath, index_only=True)
        books[name] = dict(
            title=book.title,
            modified=utils.timestr(filepath=dirpath, localtime=False, display=False),
            sum_characters=book.frontmatter["sum_characters"],
            digest=book.frontmatter["digest"],
        )

    return dict(
        software="mdbook",
        version=constants.__version__,
        now=utils.timestr(localtime=False, display=False),
        type="site",
        books=books,
    )


@rt("/update")
def get(auth):
    "Compare this local site with the update site."
    try:
        remote = utils.get_state_remote()
    except ValueError as message:
        return error(message, HTTPStatus.INTERNAL_SERVER_ERROR)
    state = get_state()
    rows = []
    books = state["books"].copy()
    for bid, rbook in remote["books"].items():
        lbook = books.pop(bid, {})
        title = lbook.get("title") or rbook.get("title")
        if lbook:
            if lbook["digest"] == rbook["digest"]:
                action = Tx("Identical")
            else:
                action = A(Tx("Differences"), href=f"/update/{bid}")
            rows.append(
                Tr(
                    Th(Strong(title), Br(), bid, scope="row"),
                    Td(
                        utils.tolocaltime(rbook["modified"]),
                        Br(),
                        f'{utils.thousands(rbook["sum_characters"])} {Tx("characters")}',
                    ),
                    Td(
                        utils.tolocaltime(lbook["modified"]),
                        Br(),
                        f'{utils.thousands(lbook["sum_characters"])} {Tx("characters")}',
                    ),
                    Td(action),
                ),
            )
        else:
            rows.append(
                Tr(
                    Th(Strong(title), Br(), bid, scope="row"),
                    Td(
                        utils.tolocaltime(rbook["modified"]),
                        Br(),
                        f'{utils.thousands(rbook["sum_characters"])} {Tx("characters")}',
                    ),
                    Td("-"),
                    Td("?"),
                )
            )
    for bid, lbook in books.items():
        rows.append(
            Tr(
                Th(bid, scope="row"),
                Td("-"),
                Td(
                    utils.tolocaltime(lbook["modified"]),
                    Br(),
                    f'{utils.thousands(lbook["sum_characters"])} {Tx("characters")}',
                ),
            ),
        )

    return (
        Title(Tx("Update")),
        components.header(title=Tx("Update")),
        Main(
            Table(
                Thead(
                    Tr(
                        Th(Tx("Book")),
                        Th(os.environ["MDBOOK_UPDATE_SITE"], scope="col"),
                        Th(Tx("Here"), scope="col"),
                        Th(scope="col"),
                    ),
                ),
                Tbody(*rows),
            ),
            cls="container",
        ),
    )


@rt("/update/{bid:str}")
def get(auth, bid: str):
    "Compare this local book with the update site book. One of them may not exist."
    if not bid:
        return error("no book id provided", HTTPStatus.BAD_REQUEST)
    try:
        remote = utils.get_state_remote(bid)
    except ValueError as message:
        return error(message, HTTPStatus.INTERNAL_SERVER_ERROR)
    try:
        book = utils.get_book(bid, refresh=True)
        state = book.state
    except KeyError:
        if bid == constants.REFERENCES:
            book = utils.get_references(refresh=True)
            state = book.state
        else:
            state = {}
    rurl = f'{os.environ["MDBOOK_UPDATE_SITE"]}/book/{bid}'
    lurl = f"/book/{bid}"
    rows = item_diffs(remote["items"], rurl, state.get("items", []), lurl)
    rows.append(
        Tr(
            Td(),
            Td(
                Form(
                    Button(f'{Tx("Update")} {os.environ["MDBOOK_UPDATE_SITE"]}'),
                    action=f"/push/{bid}",
                    method="post",
                ),
                colspan=1,
            ),
            Td(
                Form(
                    Button(f'{Tx("Update")} {Tx("here")}'),
                    action=f"/pull/{bid}",
                    method="post",
                ),
                colspan=3,
            ),
        )
    )
    return (
        Title(f'{Tx("Update")} {bid}'),
        components.header(title=f'{Tx("Update")} {bid}'),
        Main(
            Table(
                Thead(
                    Tr(
                        Th(),
                        Th(A(rurl, href=rurl), colspan=1, scope="col"),
                        Th(A(bid, href=lurl), colspan=3, scope="col"),
                    ),
                    Tr(
                        Th(Tx("Title"), scope="col"),
                        Th(),
                        Th(Tx("Age"), scope="col"),
                        Th(Tx("Size"), scope="col"),
                        Th(),
                    ),
                ),
                Tbody(*rows),
            ),
            cls="container",
        ),
    )


def item_diffs(ritems, rurl, litems, lurl):
    "Return list of rows specifying differences between remote and local items."
    result = []
    for ritem in ritems:
        riurl = f'{rurl}/{ritem["name"]}'
        for pos, litem in enumerate(list(litems)):
            if litem["title"] != ritem["title"]:
                continue
            liurl = f'{lurl}/{litem["name"]}'
            row = row_diff(ritem, riurl, litem, liurl)
            if row:
                result.append(row)
            litems.pop(pos)
            try:
                result.extend(item_diffs(ritem["items"], riurl, litem["items"], liurl))
            except KeyError as message:
                pass
            break
        else:
            result.append(row_diff(ritem, riurl, None, None))
    for litem in litems:
        result.append(row_diff(None, None, litem, liurl))
    return result


def row_diff(ritem, riurl, litem, liurl):
    if ritem is None:
        return Tr(
            Td(Strong(litem["title"])),
            Td("-"),
            Td("-"),
            Td("-"),
            Td(A(liurl, href=liurl)),
        )
    elif litem is None:
        return Tr(
            Td(Strong(ritem["title"])),
            Td(A(riurl, href=riurl)),
            Td("-"),
            Td("-"),
            Td("-"),
        )
    if litem["digest"] == ritem["digest"]:
        return None
    if litem["modified"] < ritem["modified"]:
        age = "Older"
    elif litem["modified"] > ritem["modified"]:
        age = "Newer"
    else:
        age = "Same"
    if litem["n_characters"] < ritem["n_characters"]:
        size = "Smaller"
    elif litem["n_characters"] > ritem["n_characters"]:
        size = "Larger"
    else:
        size = "Same"
    return Tr(
        Td(Strong(ritem["title"])),
        Td(A(riurl, href=riurl)),
        Td(Tx(age)),
        Td(Tx(size)),
        Td(A(liurl, href=liurl)),
    )


@rt("/pull/{bid:str}")
def post(auth, bid: str):
    "Update book at this site by downloading it from the remote site."
    if not bid:
        return error("no book id provided", HTTPStatus.BAD_REQUEST)
    url = os.path.join(os.environ["MDBOOK_UPDATE_SITE"].rstrip("/"))
    if bid == constants.REFERENCES:
        url += "/references/tgz"
        dirpath = os.path.join(os.environ["MDBOOK_DIR"], constants.REFERENCES)
    else:
        url += f"/tgz/{bid}"
        dirpath = os.path.join(os.environ["MDBOOK_DIR"], bid)
    headers = dict(apikey=os.environ["MDBOOK_UPDATE_APIKEY"])
    response = requests.get(url, headers=headers)
    if response.status_code != HTTPStatus.OK:
        return error(f"remote error: {response.message}", HTTPStatus.BAD_REQUEST)
    if response.headers["Content-Type"] != constants.GZIP_MIMETYPE:
        return error("invalid file type from remote", HTTPStatus.BAD_REQUEST)
    content = response.content
    if not content:
        return error("empty TGZ file from remote", HTTPStatus.BAD_REQUEST)
    # Temporarily save old contents.
    old_dirpath = os.path.join(os.environ["MDBOOK_DIR"], "_old")
    os.rename(dirpath, old_dirpath)
    try:
        utils.unpack_tgzfile(dirpath, content, references=bid == constants.REFERENCES)
        # Remove old contents after successful unpacking of new.
        shutil.rmtree(old_dirpath)
    except ValueError as message:
        # Reinstate old contents.
        os.rename(old_dirpath, dirpath)
        return error(
            f"error reading TGZ file from remote: {message}", HTTPStatus.BAD_REQUEST
        )
    if bid == constants.REFERENCES:
        return RedirectResponse("/references", status_code=HTTPStatus.SEE_OTHER)
    else:
        return RedirectResponse(f"/book/{bid}", status_code=HTTPStatus.SEE_OTHER)


@rt("/push/{bid:str}")
def post(auth, bid: str):
    "Update book at the remote site by uploading it from this site."
    if not bid:
        return error("no book id provided", HTTPStatus.BAD_REQUEST)
    url = f'{os.path.join(os.environ["MDBOOK_UPDATE_SITE"].rstrip("/"))}/receive/{bid}'
    dirpath = os.path.join(os.environ["MDBOOK_DIR"], bid)
    tgzfile = utils.get_tgzfile(dirpath)
    tgzfile.seek(0)
    headers = dict(apikey=os.environ["MDBOOK_UPDATE_APIKEY"])
    response = requests.post(
        url,
        headers=headers,
        files=dict(tgzfile=("tgzfile", tgzfile, constants.GZIP_MIMETYPE)),
    )
    if response.status_code != HTTPStatus.OK:
        error(f"remote did not accept push: {response.content}", HTTPStatus.BAD_REQUEST)
    print(response.content)
    return RedirectResponse("/", status_code=HTTPStatus.SEE_OTHER)


@rt("/receive/{bid:str}")
async def post(auth, bid: str, tgzfile: UploadFile = None):
    "Update book at this site by another site uploading it."
    if not bid:
        return error("book bid may not be empty", HTTPStatus.BAD_REQUEST)
    if bid.startswith("_"):
        return error(
            "book bid may not start with an underscore '_'", HTTPStatus.BAD_REQUEST
        )
    content = await tgzfile.read()
    if not content:
        return error("no content in TGZ file", HTTPStatus.BAD_REQUEST)
    dirpath = os.path.join(os.environ["MDBOOK_DIR"], bid)
    if os.path.exists(dirpath):
        # Temporarily save old contents.
        old_dirpath = os.path.join(os.environ["MDBOOK_DIR"], "_old")
        os.rename(dirpath, old_dirpath)
    else:
        old_dirpath = None
    try:
        utils.unpack_tgzfile(dirpath, content)
        if old_dirpath:
            shutil.rmtree(old_dirpath)
    except ValueError as message:
        if old_dirpath:
            os.rename(old_dirpath, dirpath)
        return error(f"error reading TGZ file: {message}", HTTPStatus.BAD_REQUEST)
    return "success"


serve()
