"""The desk never sees the answer key: shipping code does not import the simulator or the evaluation and does
not name the truth file."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "tnd"
SHIPPING = [p for p in ROOT.rglob("*.py") if p.parts[-2] not in ("sim", "evals") and p.name != "cli.py"]


def test_shipping_code_does_not_import_the_simulator_or_the_evaluation():
    assert SHIPPING
    for p in SHIPPING:
        tree = ast.parse(p.read_text())
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [("." * node.level) + (node.module or "")]
            for n in names:
                assert "sim" not in n.split(".") and "evals" not in n.split("."), f"{p}: imports {n}"


def test_shipping_code_never_names_the_answer_key():
    for p in SHIPPING:
        assert "truth" not in p.read_text(), p
