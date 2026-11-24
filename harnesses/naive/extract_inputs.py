"""Turns a task's input files into plain text. Runs inside the task container.

Uses only the standard library, plus PyMuPDF / pypdf, python-docx and openpyxl when the task
image has them. A file that cannot be turned into text is listed with the reason.

  python3 extract_inputs.py --out FILE [--per-file N] [--total N] ROOT [ROOT ...]

Writes JSON: {"files": [{"path", "kind", "bytes", "text", "truncated", "note"}], "skipped": [...]}
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "tools", ".apps_data",
             "site-packages", ".cache"}
TEXT_EXT = {".txt", ".md", ".csv", ".tsv", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
            ".py", ".js", ".ts", ".html", ".htm", ".xml", ".eml", ".log", ".ifc", ".sql", ".tex",
            ".rst", ".dat", ".inp", ".out", ".sh", ".bat", ".m", ".r", ".geojson", ".svg", ".dxf"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp"}
MAX_FILES = 2000


def read_text(path):
    with open(path, "rb") as f:
        data = f.read()
    return data.decode("utf-8", errors="replace")


def pdf_text(path):
    try:
        import fitz  # PyMuPDF
        with fitz.open(path) as doc:
            return "\n".join(f"[page {i + 1}]\n{page.get_text()}" for i, page in enumerate(doc))
    except ImportError:
        pass
    try:
        import pypdf
        reader = pypdf.PdfReader(path)
        return "\n".join(f"[page {i + 1}]\n{p.extract_text() or ''}" for i, p in enumerate(reader.pages))
    except ImportError:
        pass
    if shutil.which("pdftotext"):
        out = subprocess.run(["pdftotext", "-layout", path, "-"], capture_output=True, timeout=120)
        return out.stdout.decode("utf-8", errors="replace")
    raise RuntimeError("no PDF text tool in this container")


def docx_text(path):
    try:
        import docx
    except ImportError:
        docx = None
    if docx is not None:
        d = docx.Document(path)
        parts = [p.text for p in d.paragraphs]
        for ti, table in enumerate(d.tables):
            parts.append(f"[table {ti + 1}]")
            for row in table.rows:
                parts.append(" | ".join(c.text.strip() for c in row.cells))
        return "\n".join(parts)
    # fallback: the raw text runs of word/document.xml
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8", errors="replace")
    xml = re.sub(r"</w:p>", "\n", xml)
    return re.sub(r"<[^>]+>", "", xml)


def xlsx_text(path):
    try:
        import openpyxl
    except ImportError:
        raise RuntimeError("no spreadsheet reader (openpyxl) in this container")
    wb = openpyxl.load_workbook(path, data_only=False, read_only=True)
    parts = []
    for ws in wb.worksheets:
        parts.append(f"[sheet {ws.title}]")
        for row in ws.iter_rows(values_only=True):
            if any(v is not None for v in row):
                parts.append(",".join("" if v is None else str(v) for v in row))
    return "\n".join(parts)


def extract(path):
    """Returns (kind, text or None, note)."""
    ext = os.path.splitext(path)[1].lower()
    if ext in IMAGE_EXT:
        return "image", None, "image: not included as text"
    try:
        if ext == ".pdf":
            return "pdf", pdf_text(path), ""
        if ext in (".docx", ".docm"):
            return "docx", docx_text(path), ""
        if ext in (".xlsx", ".xlsm"):
            return "xlsx", xlsx_text(path), "cell formulas shown as written"
        if ext in TEXT_EXT or ext == "":
            text = read_text(path)
            if "\x00" in text[:4000]:
                return "binary", None, "binary file: not included"
            return "text", text, ""
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return ext.lstrip(".") or "file", None, f"could not extract text: {type(exc).__name__}: {exc}"
    return ext.lstrip(".") or "file", None, f"{ext} file: no text extraction for this format"


def walk(roots):
    seen = set()
    for root in roots:
        if not os.path.exists(root):
            continue
        real_root = os.path.realpath(root)
        if real_root in seen:
            continue
        seen.add(real_root)
        for folder, dirs, names in os.walk(real_root):
            dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith("."))
            for name in sorted(names):
                yield os.path.join(folder, name)


def fair_cap(lengths, total, per_file):
    """The largest per-file length c (at most per_file) with sum(min(n, c)) <= total."""
    lengths = sorted(min(n, per_file) for n in lengths)
    remaining, count = total, len(lengths)
    for n in lengths:
        if n * count > remaining:
            return remaining // count
        remaining -= n
        count -= 1
    return per_file


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("roots", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--per-file", type=int, default=60000)
    ap.add_argument("--total", type=int, default=500000)
    a = ap.parse_args()

    files, skipped = [], []
    for i, path in enumerate(walk(a.roots)):
        if i >= MAX_FILES:
            skipped.append({"path": path, "note": f"more than {MAX_FILES} files: not listed"})
            continue
        kind, text, note = extract(path)
        files.append({"path": path, "kind": kind, "bytes": os.path.getsize(path),
                      "text": text.strip() if text is not None else None,
                      "truncated": False, "note": note})

    # Share the budget fairly: every file keeps its whole text if all fits; otherwise the
    # longest files are all cut to the same length, so no file is starved by alphabetical order.
    cap = fair_cap([len(f["text"]) for f in files if f["text"]], a.total, a.per_file)
    for f in files:
        if f["text"] and len(f["text"]) > cap:
            f["text"], f["truncated"] = f["text"][:cap], True
    used = sum(len(f["text"]) for f in files if f["text"])
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump({"files": files, "skipped": skipped, "chars": used}, f)
    print(json.dumps({"files": len(files), "chars": used,
                      "with_text": sum(1 for x in files if x["text"]),
                      "truncated": sum(1 for x in files if x["truncated"])}))


if __name__ == "__main__":
    sys.exit(main())
