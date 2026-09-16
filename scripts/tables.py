"""Tables whose columns come in groups, drawn so the groups can be told apart.

A Markdown table has one header row and no way to say that three columns belong together. These
are emitted as HTML tables instead: a first header row names each group and spans its columns, a
second names the columns, and the cells of a group carry a tint, so "one commit per row" in Dolt,
DoltgreSQL and DoltLite sit under one label and one shade. GitHub keeps `colspan`, `rowspan` and
`align` and drops inline styles, so there the grouping is the two-row header; a viewer that keeps
styles (an editor's preview, the console page) shows the shading too. A shaded cell also fixes its
text colour, so a dark theme does not put light text on the light tint.
"""
import re

TINT = {"commit": "#eef3f8",      # the Dolt engines' stores with one commit
        "history": "#fdf1dc",     # a commit per row: history, the expensive part
        "ratio": "#f3f0fa"}       # a multiple of the baseline


def md_inline(text):
    """The little Markdown the cell emitters use, as HTML: bold, code, links."""
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    return text


def _attrs(align=None, tint=None):
    out = f' align="{align}"' if align else ""
    if align == "right":
        out += " nowrap"   # a quantity stays on one line; a wide table scrolls rather than wraps its numbers
    if tint:
        out += f' style="background:{tint};color:#24292f" bgcolor="{tint}"'
    return out


def grouped_table(fixed, groups, rows):
    """fixed: [(header, align[, width])] -- the leading columns, whose header spans both header rows.
    groups: [(label, [(sub_header, tint_or_None), ...], group_tint)] -- a column group, its
    columns (a column's own tint wins over the group's), and the group's tint (None for none).
    rows: [[cell, ...]] -- Markdown-flavoured cell text, len(fixed) + every group's columns."""
    fixed = [(f[0], f[1], f[2] if len(f) > 2 else None) for f in fixed]
    cols = [(sub, tint if tint is not None else gtint) for _, subs, gtint in groups for sub, tint in subs]
    top = "".join(f'<th rowspan="2"{_attrs(align)}{f" width={w}" if w else ""}>{md_inline(h)}</th>' for h, align, w in fixed)
    top += "".join(f'<th colspan="{len(subs)}" align="center"{_attrs(None, gtint)}>{md_inline(label)}</th>'
                   for label, subs, gtint in groups)
    second = "".join(f'<th{_attrs("right", tint)}>{md_inline(sub)}</th>' for sub, tint in cols)
    body = []
    for row in rows:
        assert len(row) == len(fixed) + len(cols), (len(row), len(fixed), len(cols))
        cells = "".join(f'<td{_attrs(align)}>{md_inline(str(c))}</td>' for c, (_, align, _) in zip(row, fixed))
        cells += "".join(f'<td{_attrs("right", tint)}>{md_inline(str(c))}</td>'
                         for c, (_, tint) in zip(row[len(fixed):], cols))
        body.append(f"<tr>{cells}</tr>")
    return ("<table>\n<thead>\n<tr>" + top + "</tr>\n<tr>" + second + "</tr>\n</thead>\n<tbody>\n"
            + "\n".join(body) + "\n</tbody>\n</table>")
