"""Move Studio local state to a clean session namespace."""

from pathlib import Path


path = Path(__file__).parents[1] / "studio_ui" / "assets" / "index-CleanStudio.js"
text = path.read_text(encoding="utf-8")
old = "var Lt=`xyue-h3-studio-session:`"
new = "var Lt=`xyue-h3-studio-session-v2:`"
if text.count(old) != 1:
    raise SystemExit("Studio session namespace not found")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
