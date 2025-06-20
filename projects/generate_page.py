import pandas as pd

df = pd.read_csv("final_projects_filtered.csv")

html = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>CS224R Final Projects</title>
    <style>
        body {
            font-family: 'Helvetica Neue', sans-serif;
            margin: 40px;
            background-color: white;
            color: #222;
        }
        a {
            color: #0056b3;
            text-decoration: none;
        }
        a:hover {
            text-decoration: underline;
        }
        .back {
            margin-bottom: 20px;
            display: inline-block;
            font-size: 0.95em;
        }
        h1 {
            text-align: center;
            margin-bottom: 20px;
        }
        #search {
            display: block;
            margin: 0 auto 30px auto;
            padding: 8px;
            width: 60%;
            font-size: 1em;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            table-layout: fixed;
        }
        th, td {
            padding: 12px 16px;
            border-bottom: 1px solid #ddd;
            vertical-align: top;
        }
        th {
            background-color: #f3f3f3;
            text-align: left;
            font-weight: 600;
        }
        tr:hover {
            background-color: #fafafa;
        }
        .outstanding-row {
            background-color: #fff8e1;
            font-weight: 500;
        }
        .outstanding-title {
            color: #d48806;
            font-weight: 600;
        }
    </style>
    <script>
        function filterTable() {
            var input = document.getElementById("search");
            var filter = input.value.toLowerCase();
            var rows = document.getElementsByTagName("tr");
            for (let i = 1; i < rows.length; i++) {
                let text = rows[i].innerText.toLowerCase();
                rows[i].style.display = text.includes(filter) ? "" : "none";
            }
        }
    </script>
</head>
<body>
    <a class="back" href="index.html">&#8592; Back to Home</a>
    <h1>CS224R Final Projects</h1>
    <input type="text" id="search" onkeyup="filterTable()" placeholder="Search by keyword, title, author, etc.">
    <table>
        <thead>
            <tr>
                <th>Type</th>
                <th>Title</th>
                <th>Authors</th>
                <th>Mentor TA</th>
            </tr>
        </thead>
        <tbody>
"""

for _, row in df.iterrows():
    type_ = row["Type"]
    title = row["Title"]
    authors = row["Authors"]
    ta = row["Mentor TA"] if pd.notna(row["Mentor TA"]) else "—"
    pdf = row["PDF"]

    # check if outstanding 
    is_outstanding = title.startswith("Outstanding Project")

    # highlight outstanding in styled span
    if is_outstanding:
        prefix = '<span class="outstanding-title">Outstanding Project:</span>'
        suffix = title.replace("Outstanding Project:", "").strip()
        display_title = f"{prefix} {suffix}"
        row_class = "outstanding-row"
    else:
        display_title = title
        row_class = ""

    # build html
    title_link = f'<a href="./pdfs/{pdf}" target="_blank"><strong>{display_title}</strong></a>'
    html += f"""
        <tr class="{row_class}">
            <td>{type_}</td>
            <td>{title_link}</td>
            <td>{authors}</td>
            <td>{ta}</td>
        </tr>
    """

html += """
        </tbody>
    </table>
</body>
</html>
"""

with open("cs224r_final_projects.html", "w") as f:
    f.write(html)
