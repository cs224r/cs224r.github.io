"""Render cs224r_final_projects.html from final_projects.csv.

Rows are sorted by title. A title starting with "Outstanding Project:"
gets a gold badge and a highlighted row, same convention as the 2025 CSV.

The page reuses the main site's stylesheets (css/bootstrap.min.css and
css/style.css) so it looks like the rest of cs224r.stanford.edu.
"""
import csv
import html
import re
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).parent
CSV_PATH = ROOT / "final_projects.csv"
OUT_HTML = ROOT / "cs224r_final_projects.html"

TERM = "Spring 2026"

PAGE = """<!DOCTYPE html>
<html lang="en">

<head>
    <meta charset="utf-8">
    <title>CS 224R Final Projects</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="description" content="Final project reports from CS 224R Deep Reinforcement Learning, Stanford University, __TERM__.">

    <link href="../css/bootstrap.min.css" rel="stylesheet">
    <link href="../css/style.css" rel="stylesheet">

    <style>
        .back-link {
            display: inline-block;
            margin-top: 18px;
            font-size: 15px;
        }
        #search {
            max-width: 460px;
            margin: 4px 0 6px;
        }
        #count {
            color: #666;
            font-size: 14px;
            min-height: 20px;
            margin-bottom: 12px;
        }
        table.projects {
            table-layout: fixed;
            margin-bottom: 10px;
        }
        table.projects th {
            background-color: #f3f3f3;
            position: sticky;
            top: 0;
        }
        table.projects th.col-type { width: 9%; }
        table.projects th.col-title { width: 51%; }
        table.projects th.col-ta { width: 15%; }
        table.projects th, table.projects td {
            padding: 10px 14px;
            vertical-align: top;
        }
        td.authors, td.type, td.ta { color: #666; }
        tr.outstanding-row,
        .table-hover > tbody > tr.outstanding-row:hover > td {
            background-color: #fff8e1;
        }
        .label-outstanding { background-color: #b8860b; }
        #noresults {
            display: none;
            padding: 24px 14px;
            color: #666;
        }
        @media (max-width: 700px) {
            table.projects thead { display: none; }
            table.projects, table.projects tbody { display: block; width: 100%; }
            table.projects tr {
                display: flex;
                flex-direction: column;
                border-top: 1px solid #ddd;
                padding: 10px 0;
            }
            table.projects td { display: block; width: 100%; border-top: none; padding: 2px 8px; }
            td.title { order: 1; }
            td.authors { order: 2; }
            td.type, td.ta { order: 3; font-size: 14px; color: #888; }
            td.type::before { content: "Track: "; }
            td.ta::before { content: "Mentor TA: "; }
        }
    </style>
</head>

<body>
    <div class="container">
        <div class="row clearfix">
            <div class="col-md-12 column">
                <a class="back-link" href="../index.html">&#8592; Back to CS 224R Home</a>

                <h1>CS 224R Final Projects</h1>
                <h3>__TERM__ &middot; __COUNT__ student projects</h3>
                <p>Final project reports from CS 224R Deep Reinforcement Learning.
                    Click a title to open the report (PDF, new tab).</p>

                <input type="text" id="search" class="form-control"
                    placeholder="Search by title or author..." autocomplete="off"
                    aria-label="Search projects">
                <div id="count"></div>

                <table class="table table-hover projects">
                    <thead>
                        <tr>
                            <th class="col-type">Type</th>
                            <th class="col-title">Title</th>
                            <th>Authors</th>
                            <th class="col-ta">Mentor TA</th>
                        </tr>
                    </thead>
                    <tbody id="rows">
__ROWS__
                    </tbody>
                </table>
                <div id="noresults">No projects match your search.</div>

                <!-- The footer -->
                <div class="hrline">
                    <hr>
                </div><br>
                <div class="row clearfix">
                    <div class="col-md-3 column">
                    </div>
                    <div class="col-md-6 column">
                        <div class="text-center">
                            <p>
                                &nbsp;&nbsp;&nbsp; &#169; Chelsea Finn 2026
                            </p>
                        </div>
                    </div>
                    <div class="col-md-3 column">
                    </div>
                </div>
                <br>
                <br>
            </div>
        </div>
    </div>

    <script>
        var input = document.getElementById("search");
        var countEl = document.getElementById("count");
        var noResults = document.getElementById("noresults");
        var rows = Array.prototype.slice.call(document.getElementById("rows").rows);
        var haystacks = rows.map(function (r) { return r.innerText.toLowerCase(); });
        var total = rows.length;

        function applyFilter() {
            var q = input.value.trim().toLowerCase();
            var shown = 0;
            for (var i = 0; i < rows.length; i++) {
                var hit = !q || haystacks[i].indexOf(q) !== -1;
                rows[i].style.display = hit ? "" : "none";
                if (hit) shown++;
            }
            countEl.textContent = q ? shown + " of " + total + " projects" : "";
            noResults.style.display = shown ? "none" : "block";
        }

        input.addEventListener("input", applyFilter);
        input.addEventListener("keydown", function (e) {
            if (e.key === "Escape") { input.value = ""; applyFilter(); input.blur(); }
        });
        document.addEventListener("keydown", function (e) {
            if (e.key === "/" && document.activeElement !== input) { e.preventDefault(); input.focus(); }
        });
    </script>
</body>

</html>
"""

OUTSTANDING_PREFIX = "Outstanding Project:"


def sort_key(title):
    return re.sub(r"^[^A-Za-z0-9]+", "", title).casefold()


def main():
    with open(CSV_PATH, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    rows.sort(key=lambda r: sort_key(r["Title"]))
    # outstanding projects float to the top, like the 2025 page
    rows.sort(key=lambda r: 0 if r["Title"].startswith(OUTSTANDING_PREFIX) else 1)

    body = []
    for row in rows:
        title, authors, pdf = row["Title"], row["Authors"], row["PDF"]
        ptype = row.get("Type", "") or "&mdash;"
        ta = html.escape(row.get("Mentor TA", "")) or "&mdash;"
        outstanding = title.startswith(OUTSTANDING_PREFIX)
        badge = ""
        if outstanding:
            title = title[len(OUTSTANDING_PREFIX):].strip()
            badge = '<span class="label label-outstanding">Outstanding Project</span> '
        if pdf:
            href = "./pdfs/" + quote(pdf)
            title_cell = f'<a href="{href}" target="_blank" rel="noopener"><b>{html.escape(title)}</b></a>'
        else:
            # report withheld at the authors' request; only the title is listed
            title_cell = f"<b>{html.escape(title)}</b>"
        body.append(
            f'                        <tr{" class=\"outstanding-row\"" if outstanding else ""}>\n'
            f'                            <td class="type">{ptype}</td>\n'
            f'                            <td class="title">{badge}{title_cell}</td>\n'
            f'                            <td class="authors">{html.escape(authors)}</td>\n'
            f'                            <td class="ta">{ta}</td>\n'
            f"                        </tr>"
        )

    page = (
        PAGE.replace("__TERM__", TERM)
        .replace("__COUNT__", str(len(rows)))
        .replace("__ROWS__", "\n".join(body))
    )
    OUT_HTML.write_text(page, encoding="utf-8")
    print(f"wrote {OUT_HTML.name} with {len(rows)} rows")


if __name__ == "__main__":
    main()
