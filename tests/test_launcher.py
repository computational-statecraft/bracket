"""The page→app bridge in the app's own window: saving exports."""
import base64

import launcher


def test_only_export_types_with_plain_names_are_saved(tmp_path):
    files = [
        {"name": "statement.docx", "b64": base64.b64encode(b"PK").decode()},
        {"name": "history.md", "text": "# h"},
        {"name": "../../escape.md", "text": "x"},          # folders stripped: lands in the folder as a plain name
        {"name": "run.command", "text": "rm -rf ~"},       # a script: refused
        {"name": "Evil.app", "text": "x"},
        {"name": ".zshrc", "text": "x"},                   # hidden file: refused
        {"name": "noext", "text": "x"},
        "not a dict",
    ]
    saved = launcher._save_exports(tmp_path, files)
    names = sorted(p.name for p in tmp_path.iterdir())
    assert names == ["escape.md", "history.md", "statement.docx"] and len(saved) == 3
    assert all(str(tmp_path) in s for s in saved)


def test_the_bridge_has_no_way_to_open_arbitrary_addresses():
    assert not hasattr(launcher._Bridge, "open_in_browser")
