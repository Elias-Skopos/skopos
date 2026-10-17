"""Small adapter for pywebview 6.2's otherwise all-files-only Save dialog."""
from pathlib import Path


def configure_csv_dialog(dialog, filename):
    dialog.Title = "Salvar arquivo CSV"
    dialog.Filter = "Arquivo CSV (*.csv)|*.csv|Todos os arquivos (*.*)|*.*"
    dialog.DefaultExt = "csv"
    dialog.AddExtension = True
    dialog.OverwritePrompt = True
    dialog.RestoreDirectory = True
    dialog.FileName = Path(filename).name


def install_download_handler(renderer):
    if renderer != "edgechromium":
        return
    from webview.platforms import edgechromium as edge

    original = edge.EdgeChrome.on_download_starting
    if getattr(original, "_skopos_csv", False):
        return

    def download(browser, sender, args):
        filename = str(args.ResultFilePath)
        if Path(filename).suffix.lower() != ".csv":
            return original(browser, sender, args)
        if not edge.webview_settings["ALLOW_DOWNLOADS"]:
            args.Cancel = True
            return
        dialog = edge.WinForms.SaveFileDialog()
        try:
            configure_csv_dialog(dialog, filename)
            downloads = Path.home() / "Downloads"
            if downloads.is_dir():
                dialog.InitialDirectory = str(downloads)
            while dialog.ShowDialog(browser.form) == edge.WinForms.DialogResult.OK:
                selected = str(dialog.FileName)
                if selected.lower().endswith(".csv"):
                    args.ResultFilePath = selected
                    break
                # Re-open with the correct extension so the native dialog also
                # checks for an existing CSV before approving an overwrite.
                dialog.FileName = selected + ".csv"
            else:
                args.Cancel = True
        finally:
            dialog.Dispose()

    download._skopos_csv = True
    edge.EdgeChrome.on_download_starting = download
