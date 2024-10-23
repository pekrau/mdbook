"Page components."

import psutil

from fasthtml.common import *

import constants
import utils
from book import Book
from utils import Tx


NAV_STYLE_TEMPLATE = "outline-color: {color}; outline-width:8px; outline-style:solid; padding:0px 10px; border-radius:5px;"


def metadata(item):
    "Display status, n words and n characters."
    return "; ".join(
        [
            Tx(item.type),
            Tx(repr(item.status)),
            f'{utils.thousands(item.n_words)} {Tx("words")}',
            f'{utils.thousands(item.n_characters)} {Tx("characters")}',
        ]
    )


def header(book=None, item=None, title=None, actions=None, state_url=None):
    "The standard page header with navigation bar."
    # The first cell: icon and book title (if any).
    if book:
        entries = [
            Ul(
                Li(A(Img(src="/mdbook.png", width=32, height=32), href="/")),
                Li(A(Strong(book.title), href=f"/book/{book.name}")),
            )
        ]
    else:
        entries = [Ul(Li(A(Img(src="/mdbook.png"), href="/")))]

    # The second cell: title, or item info, or book info.
    if title:
        entries.append(Ul(Li(Strong(title))))
        if book is None:
            nav_style = NAV_STYLE_TEMPLATE.format(color="black")
        else:
            nav_style = NAV_STYLE_TEMPLATE.format(color=book.status.color)

    elif item:
        entries.append(
            Ul(
                Li(
                    Strong(item.fulltitle),
                    Br(),
                    Small(metadata(item)),
                )
            )
        )
        nav_style = NAV_STYLE_TEMPLATE.format(color=item.status.color)

    elif book:
        entries.append(
            Ul(
                Li(
                    f"{Tx(repr(book.status))}; ",
                    f'{utils.thousands(book.sum_words)} {Tx("words")}; '
                    f'{utils.thousands(book.sum_characters)} {Tx("characters")}; ',
                    f'{Tx("language")}: {book.frontmatter.get("language") or "-"}',
                )
            )
        )
        nav_style = NAV_STYLE_TEMPLATE.format(color=book.status.color)

    else:
        nav_style = NAV_STYLE_TEMPLATE.format(color="black")

    pages = []
    if item is not None:
        if item.parent:
            if item.parent.level == 0:  # Book.
                url = f"/book/{book.name}"
            else:
                url = f"/book/{book.name}/{item.parent.path}"
            pages.append(A(NotStr(f"&ShortUpArrow; {item.parent.title}"), href=url))
        if item.prev:
            url = f"/book/{book.name}/{item.prev.path}"
            pages.append(A(NotStr(f"&ShortLeftArrow; {item.prev.title}"), href=url))
        if item.next:
            url = f"/book/{book.name}/{item.next.path}"
            pages.append(A(NotStr(f"&ShortRightArrow; {item.next.title}"), href=url))
    if book is not None:
        pages.append(A(Tx("Title"), href=f"/title/{book.name}"))
        pages.append(A(Tx("Index"), href=f"/index/{book.name}"))
        pages.append(A(Tx("Status list"), href=f"/statuslist/{book.name}"))
    pages.append(A(Tx("References"), href="/references"))
    pages.append(A(Tx("Information"), href="/information"))
    if state_url:
        pages.append(A(Tx("State"), href=state_url))
    items = [
        Li(Details(Summary(Tx("Pages")), Ul(*[Li(p) for p in pages]), cls="dropdown"))
    ]
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
    entries.append(Ul(*items))
    return Header(Nav(*entries, style=nav_style), cls="container")


def toc(book, items, show_arrows=False):
    "Recursive lists of sections and texts."
    parts = []
    for item in items:
        if show_arrows:
            arrows = [
                NotStr("&nbsp;"),
                A(NotStr("&ShortUpArrow;"), href=f"/up/{book.name}/{item.path}"),
                NotStr("&nbsp;"),
                A(NotStr("&ShortDownArrow;"), href=f"/down/{book.name}/{item.path}"),
            ]
        else:
            arrows = []
        parts.append(
            Li(
                A(
                    str(item),
                    style=f"color: {item.status.color};",
                    href=f"/book/{book.name}/{item.path}",
                ),
                NotStr("&nbsp;&nbsp;&nbsp;"),
                Small(metadata(item)),
                *arrows,
            )
        )
        if item.is_section:
            parts.append(toc(book, item.items, show_arrows=show_arrows))
    return Ol(*parts)


def footer(item):
    return Footer(
        Hr(), Small(f'{Tx("Modified")}: ', Time(item.modified)), cls="container"
    )
