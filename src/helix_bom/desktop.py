"""
The no-terminal way in: pick a file, get a report.

Installed as ``helix-bom-gui``. On Windows that is a windowed executable, so
double-clicking it opens the file picker and never flashes a console.

This is deliberately thin. It picks a file, runs the same review the command
line runs, writes the same report and opens it. Every check, every finding and
every "not checked" reason comes from the same code path -- a second
implementation that drifted from the first would be worse than no window at
all, because the two would disagree and only one of them would be tested.

tkinter is imported inside the functions that need it. It is in the standard
library but not in every Linux distribution's base python package, and a
missing dialog toolkit should produce a sentence rather than an ImportError
traceback at module load.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

FILETYPES = [
    ("BOM and netlist files", "*.csv *.tsv *.txt *.net"),
    ("CSV files", "*.csv"),
    ("KiCad netlists", "*.net"),
    ("All files", "*.*"),
]


def _error(title: str, message: str) -> None:
    """Say it in a window if we can, on stderr if we cannot."""
    try:
        from tkinter import messagebox
        messagebox.showerror(title, message)
    except Exception:                                    # noqa: BLE001
        print(f"{title}: {message}", file=sys.stderr)


def choose_file(argv=None):
    """The path to review, from the command line or a picker.

    Passing a path is what makes "drag a BOM onto the icon" work on every
    desktop, so it is checked before anything is opened.
    """
    argv = sys.argv[1:] if argv is None else argv
    if argv:
        candidate = Path(argv[0])
        return candidate if candidate.exists() else None

    from tkinter import Tk, filedialog

    root = Tk()
    root.withdraw()                 # no empty window behind the dialog
    try:
        chosen = filedialog.askopenfilename(
            title="Choose a BOM export or a KiCad netlist",
            filetypes=FILETYPES)
    finally:
        root.destroy()
    return Path(chosen) if chosen else None


def review(path: Path) -> Path:
    """Run the review and write the report. Returns where it landed."""
    from .cli import _looks_like_netlist, _version_line
    from .distributors import LookupCache, live_distributors
    from .enrich import enrich
    from .ingest import load_bom
    from .report import default_destination, write_html

    nets = []
    if _looks_like_netlist(path):
        from .netlist import load_netlist
        components, nets, ingest_report = load_netlist(path)
    else:
        components, ingest_report = load_bom(path)

    if not components:
        raise ValueError(
            f"No component lines were read from {path.name}.\n\n"
            "The file may use headings this tool does not recognise yet. "
            "Running `helix-bom diagnose` on it prints the structure and none "
            "of the contents, which is safe to share in a bug report.")

    report = enrich(components, live_distributors(os.environ),
                    cache=LookupCache())

    diagram = ""
    if nets:
        from .diagrams import generate_netlist_interconnect_svg
        from .netlist import interconnect_from_nets
        diagram = generate_netlist_interconnect_svg(
            interconnect_from_nets(nets),
            source=getattr(ingest_report, "source", ""))

    return write_html(report, default_destination(path), ingest=ingest_report,
                      source=path, diagram_svg=diagram,
                      version=_version_line())


def main(argv=None) -> int:
    try:
        path = choose_file(argv)
    except ImportError:
        _error("helix-bom",
               "This needs tkinter, which is missing from this Python.\n\n"
               "On Debian or Ubuntu: sudo apt install python3-tk\n"
               "Or use the command line: helix-bom enrich <file> --html")
        return 2

    if path is None:
        return 0                    # cancelled, which is not a failure

    try:
        destination = review(path)
    except ValueError as exc:
        _error("Could not read that file", str(exc))
        return 2
    except OSError as exc:
        _error("Could not write the report", str(exc))
        return 2

    from .report import open_in_browser
    if not open_in_browser(destination):
        _error("Report written",
               f"The report is at:\n\n{destination}\n\n"
               "No browser could be opened automatically.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
