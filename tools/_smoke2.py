import sys; sys.path.insert(0,".")
from hushplayer.lyrics.parser import parse
d = parse("[00:01.00]<00:01.00>hello <00:01.60>world\n[00:03.00]<00:03.00>bye")
print("synced", d.synced, "kind", d.kind)
for ln in d.lines:
    print(ln.start_ms, ln.end_ms, repr(ln.text), [(w.text, w.start_ms, w.end_ms) for w in ln.words])
d2 = parse("[1000,4000](0,600,0)你(600,600,0)好(1200,800,0)世界\n[5000,3000](0,500,0)再见")
print("klyric", d2.synced, len(d2.lines), d2.has_word_timing)
for ln in d2.lines:
    print(ln.start_ms, ln.end_ms, repr(ln.text), [(w.text, w.start_ms, w.end_ms) for w in ln.words])
print("idx", d2.index_at(1500), d2.line_progress(0, 1500), d2.word_progress(0, 1500))
d3 = parse("第一行\n第二行")
print("plain", d3.synced, d3.kind, len(d3.lines))
d4 = parse("此歌曲为没有填词的纯音乐，请您静候")
print("instr", d4.kind, len(d4.lines))
