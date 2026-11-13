"""One-command reproducible launcher for MBV V0.1 SYNTHETIC_DEMO."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mbv.cli import main  # noqa: E402


if __name__ == "__main__":
    default_args = [
        "demo",
        "--examples-dir",
        str(ROOT / "examples"),
        "--outdir",
        str(ROOT / "examples" / "demo_outputs"),
        "--config",
        str(ROOT / "config" / "default.yaml"),
    ]
    argv = sys.argv[1:] if len(sys.argv) > 1 else default_args
    raise SystemExit(main(argv))
