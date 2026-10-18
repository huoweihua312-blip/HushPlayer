import pathlib
p = pathlib.Path("hushplayer/online/proxy.py")
t = p.read_text(encoding="utf-8")
old = '''        if not download.complete and not download.error:
            download.start()
        if start > 0 and not download.wait_for(start):
            handler.send_error(504, "audio not ready")
            return

        path = download.dest
        if not path.exists():
            handler.send_error(502, download.error[:160] or "audio unavailable")
            return'''
new = '''        if not download.complete and not download.error:
            download.start()
        if not download.complete and not download.wait_for(max(start, 1)):
            if download.error:
                handler.send_error(502, download.error[:160] or "audio unavailable")
            else:
                handler.send_error(504, "audio not ready")
            return

        path = download.dest
        if not path.exists():
            handler.send_error(502, download.error[:160] or "audio unavailable")
            return'''
assert old in t
t = t.replace(old, new, 1)
p.write_text(t, encoding="utf-8")
print("ok")
