#!/usr/bin/env python3

from itertools import zip_longest
from sys import stdout
import time

from textual.app import App, ComposeResult
from textual.widgets import DataTable, Header, Footer, RichLog, Static, Input
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual import log
from rich.text import Text
from jinja2.filters import do_filesizeformat
import ipaddress

from fhost import db, File, AddrFilter, su, app as fhost_app
from modui import FileTable, mime, MpvWidget, Notification

fhost_app.app_context().push()


class NullptrMod(Screen):
    BINDINGS = [
        ("q", "quit_app", "Quit"),
        ("f1", "filter(1, 'Name')", "Lookup name"),
        ("f2", "filter(2, 'IP address')", "Filter IP"),
        ("f3", "filter(3, 'MIME Type')", "Filter MIME"),
        ("f4", "filter(4, 'Extension')", "Filter Ext."),
        ("f5", "refresh", "Refresh"),
        ("f6", "filter_clear", "Clear filter"),
        ("f7", "filter(5, 'User agent')", "Filter UA"),
        ("r", "remove_file(False)", "Remove file"),
        ("ctrl+r", "remove_file(True)", "Ban file"),
        ("p", "ban_ip(False)", "Ban IP"),
        ("ctrl+p", "ban_ip(True)", "Nuke IP"),
    ]

    async def action_quit_app(self):
        self.mpvw.shutdown()
        await self.app.action_quit()

    def action_refresh(self):
        ftable = self.query_one("#ftable")
        ftable.watch_query(None, None)

    def action_filter_clear(self):
        self.finput.display = False
        ftable = self.query_one("#ftable")
        ftable.focus()
        ftable.query = ftable.base_query

    def action_filter(self, fcol: int, label: str):
        self.finput.placeholder = label
        self.finput.display = True
        self.finput.focus()
        self.filter_col = fcol
        self._refresh_layout()

        if self.current_file:
            match fcol:
                case 1: self.finput.value = ""
                case 2: self.finput.value = self.current_file.addr.compressed
                case 3: self.finput.value = self.current_file.mime
                case 4: self.finput.value = self.current_file.ext
                case 5: self.finput.value = self.current_file.ua or ""

    def on_input_submitted(self, message: Input.Submitted) -> None:
        self.finput.display = False
        ftable = self.query_one("#ftable")
        ftable.focus()
        q = ftable.base_query

        if len(message.value):
            match self.filter_col:
                case 1:
                    try:
                        q = q.filter(File.id == su.debase(message.value))
                    except ValueError:
                        return
                case 2:
                    try:
                        addr = ipaddress.ip_address(message.value)
                        if type(addr) is ipaddress.IPv6Address:
                            addr = addr.ipv4_mapped or addr
                        q = q.filter(File.addr == addr)
                    except ValueError:
                        return
                case 3: q = q.filter(File.mime.like(message.value))
                case 4: q = q.filter(File.ext.like(message.value))
                case 5: q = q.filter(File.ua.like(message.value))

        ftable.query = q

    def action_remove_file(self, permanent: bool) -> None:
        if self.current_file:
            self.current_file.delete(permanent)
            db.session.commit()
            self.mount(Notification(f"{'Banned' if permanent else 'Removed'}"
                                    f"file {self.current_file.getname()}"))
            self.action_refresh()

    def action_ban_ip(self, nuke: bool) -> None:
        if self.current_file:
            addr = self.current_file.addr
            if AddrFilter.query.filter(AddrFilter.addr == addr).scalar():
                txt = f"{addr.compressed} is already banned"
            else:
                db.session.add(AddrFilter(addr))
                db.session.commit()
                txt = f"Banned {addr.compressed}"

            if nuke:
                tsize = 0
                trm = 0
                for f in File.query.filter(File.addr == addr):
                    if f.getpath().is_file():
                        tsize += f.size or f.getpath().stat().st_size
                        trm += 1
                    f.delete(True)
                db.session.commit()
                txt += f", removed {trm} {'files' if trm != 1 else 'file'} " \
                       f"totaling {do_filesizeformat(tsize, True)}"
            self.mount(Notification(txt))
            self._refresh_layout()
            ftable = self.query_one("#ftable")
            ftable.watch_query(None, None)

    def on_update(self) -> None:
        stdout.write("\033[?25l")
        stdout.flush()

    def compose(self) -> ComposeResult:
        yield Header()
        yield Horizontal(
            FileTable(id="ftable", zebra_stripes=True, cursor_type="row"),
            Vertical(
                DataTable(id="finfo", show_header=False, cursor_type="none"),
                MpvWidget(id="mpv"),
                RichLog(id="ftextlog", auto_scroll=False),
                id="infopane"))
        yield Input(id="filter_input")
        yield Footer()

    def on_mount(self) -> None:
        self.current_file = None

        self.ftable = self.query_one("#ftable")
        self.ftable.focus()

        self.finfo = self.query_one("#finfo")
        self.finfo.add_columns("key", "value")

        self.mpvw = self.query_one("#mpv")
        self.ftlog = self.query_one("#ftextlog")

        self.finput = self.query_one("#filter_input")

        self.mimehandler = mime.MIMEHandler()
        self.mimehandler.register(mime.MIMECategory.Archive,
                                  self.handle_libarchive)
        self.mimehandler.register(mime.MIMECategory.Text, self.handle_text)
        self.mimehandler.register(mime.MIMECategory.AV, self.handle_mpv)
        self.mimehandler.register(mime.MIMECategory.Document,
                                  self.handle_mupdf)
        self.mimehandler.register(mime.MIMECategory.Fallback,
                                  self.handle_libarchive)
        self.mimehandler.register(mime.MIMECategory.Fallback, self.handle_mpv)
        self.mimehandler.register(mime.MIMECategory.Fallback, self.handle_raw)

    def handle_libarchive(self, cat):
        import libarchive
        with libarchive.file_reader(str(self.current_file.getpath())) as a:
            self.ftlog.write("\n".join(e.path for e in a))
        return True

    def handle_text(self, cat):
        with open(self.current_file.getpath(), "r") as sf:
            data = sf.read(1000000).replace("\033", "")
            self.ftlog.write(data)
        return True

    def handle_mupdf(self, cat):
        import fitz
        with fitz.open(self.current_file.getpath(),
                       filetype=self.current_file.ext.lstrip(".")) as doc:
            p = doc.load_page(0)
            pix = p.get_pixmap(dpi=72)
            imgdata = pix.tobytes("ppm").hex()

            self.mpvw.styles.height = "40%"
            self.mpvw.start_mpv("hex://" + imgdata, 0)

            self.ftlog.write(
                Text.from_markup(f"[bold]Pages:[/bold] {doc.page_count}"))
            self.ftlog.write(Text.from_markup("[bold]Metadata:[/bold]"))
            for k, v in doc.metadata.items():
                self.ftlog.write(Text.from_markup(f"  [bold]{k}:[/bold] {v}"))
            toc = doc.get_toc()
            if len(toc):
                self.ftlog.write(Text.from_markup("[bold]TOC:[/bold]"))
                for lvl, title, page in toc:
                    self.ftlog.write(f"{'  ' * lvl} {page}: {title}")
        return True

    def handle_mpv(self, cat):
        if cat == mime.MIMECategory.AV or self.current_file.nsfw_score >= 0:
            self.mpvw.styles.height = "20%"
            self.mpvw.start_mpv(str(self.current_file.getpath()), 0)

            import av
            with av.open(str(self.current_file.getpath())) as c:
                self.ftlog.write(Text("Format:", style="bold"))
                self.ftlog.write(f"  {c.format.long_name}")
                if len(c.metadata):
                    self.ftlog.write(Text("Metadata:", style="bold"))
                    for k, v in c.metadata.items():
                        self.ftlog.write(f"  {k}: {v}")
                    for s in c.streams:
                        self.ftlog.write(
                            Text(f"Stream {s.index}:", style="bold"))
                        self.ftlog.write(f"  Type: {s.type}")
                        if s.base_rate:
                            self.ftlog.write(f"  Frame rate: {s.base_rate}")
                        if len(s.metadata):
                            self.ftlog.write(Text("  Metadata:", style="bold"))
                            for k, v in s.metadata.items():
                                self.ftlog.write(f"    {k}: {v}")
            return True
        return False

    def handle_raw(self, cat):
        def hexdump(binf, length):
            def fmt(s):
                if isinstance(s, str):
                    c = chr(int(s, 16))
                else:
                    c = chr(s)
                    s = c
                if c.isalpha():
                    return f"\0[chartreuse1]{s}\0[/chartreuse1]"
                if c.isdigit():
                    return f"\0[gold1]{s}\0[/gold1]"
                if not c.isprintable():
                    g = "grey50" if c == "\0" else "cadet_blue"
                    return f"\0[{g}]{s if len(s) == 2 else '.'}\0[/{g}]"
                return s

            return Text.from_markup(
                "\n".join(' '.join(
                    map(fmt, map(''.join, zip(*[iter(c.hex())] * 2)))) +
                    f"{'   ' * (16 - len(c))} {''.join(map(fmt, c))}"
                    for c in
                    map(lambda x: bytes([n for n in x if n is not None]),
                        zip_longest(
                            *[iter(binf.read(min(length, 16 * 10)))] * 16))))

        with open(self.current_file.getpath(), "rb") as binf:
            self.ftlog.write(hexdump(binf, self.current_file.size))
            if self.current_file.size > 16*10*2:
                binf.seek(self.current_file.size-16*10)
                self.ftlog.write("  [...]  ".center(64, '─'))
            self.ftlog.write(hexdump(binf,
                                     self.current_file.size - binf.tell()))

        return True

    def on_file_table_selected(self, message: FileTable.Selected) -> None:
        f = message.file
        self.current_file = f
        self.finfo.clear()
        self.finfo.add_rows([
            ("ID:", str(f.id)),
            ("File name:", f.getname()),
            ("URL:", f.geturl()
             if fhost_app.config["SERVER_NAME"]
             else "⚠ Set SERVER_NAME in config.py to display"),
            ("File size:", do_filesizeformat(f.size, True)),
            ("MIME type:", f.mime),
            ("SHA256 checksum:", f.sha256),
            ("Uploaded by:", Text(f.addr.compressed)),
            ("User agent:", Text(f.ua or "")),
            ("Management token:", f.mgmt_token),
            ("Secret:", f.secret),
            ("Is NSFW:", ("Yes" if f.is_nsfw else "No") +
             (f" (Score: {f.nsfw_score:0.4f})"
              if f.nsfw_score else " (Not scanned)")),
            ("Is banned:", "Yes" if f.removed else "No"),
            ("Expires:",
             time.strftime("%Y-%m-%d %H:%M:%S",
                           time.gmtime(File.get_expiration(f.expiration,
                                                           f.size)/1000)))
        ])

        self.mpvw.stop_mpv(True)
        self.ftlog.clear()

        if f.getpath().is_file():
            self.mimehandler.handle(f.mime, f.ext)
            self.ftlog.scroll_to(x=0, y=0, animate=False)


class NullptrModApp(App):
    CSS_PATH = "mod.css"

    def on_mount(self) -> None:
        self.title = "0x0 File Moderation Interface"
        self.main_screen = NullptrMod()
        self.install_screen(self.main_screen, name="main")
        self.push_screen("main")


if __name__ == "__main__":
    app = NullptrModApp()
    app.run()
