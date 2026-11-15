"""Native save dialog; accept the platform-specific PyWebView return formats."""

from pathlib import Path


def save_csv(window, content):
    import webview

    selected = window.create_file_dialog(
        webview.FileDialog.SAVE,
        save_filename="renmon.csv",
        file_types=("CSV (*.csv)",),
    )
    if not selected:
        return False
    path = selected if isinstance(selected, str) else selected[0]
    Path(path).write_bytes(content)
    return True
