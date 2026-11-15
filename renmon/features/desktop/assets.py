"""Load one self-contained document; never pass a local URL to PyWebView."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def document():
    html = (ROOT / "static/index.html").read_text(encoding="utf-8")
    css = (ROOT / "static/style.css").read_text(encoding="utf-8")
    script = (ROOT / "ui.bundle.js").read_text(encoding="utf-8")
    # The native bridge injects scripts/evaluates JS. Network requests remain blocked.
    policy = "default-src 'none'; script-src 'unsafe-inline' 'unsafe-eval'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'; base-uri 'none'; form-action 'none'"
    html = html.replace(
        "<head>",
        f'<head><meta http-equiv="Content-Security-Policy" content="{policy}">',
    )
    html = html.replace(
        '<link rel="stylesheet" href="/style.css" />', "<style>" + css + "</style>"
    )
    return html.replace(
        '<script type="module" src="/app.js"></script>',
        "<script>" + script.replace("</script", "<\\/script") + "</script>",
    )
