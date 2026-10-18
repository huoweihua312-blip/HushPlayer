import sys, io; sys.path.insert(0,".")
out = io.StringIO()
from hushplayer.lyrics.parser import parse
def show(tag, d):
    out.write(f"{tag}: synced={d.synced} kind={d.kind} words={d.has_word_timing} lines={len(d.lines)}\n")
    for ln in d.lines[:6]:
        out.write(f"  {ln.start_ms}-{ln.end_ms} {ln.text!r} words={[(w.text,w.start_ms,w.end_ms) for w in ln.words]}\n")
show("enhanced", parse("[00:01.00]<00:01.00>hello <00:01.60>world\n[00:03.00]<00:03.00>bye"))
show("yrc", parse("[1000,4000](0,600,0)你(600,600,0)好(1200,800,0)世界\n[5000,3000](0,500,0)再见"))
show("qrc", parse("[1000,4000]你(0,600)好(600,600)世界(1200,800)\n[5000,3000]再见(0,500)"))
show("plain", parse("第一行\n第二行\n第三行"))
show("instr", parse("此歌曲为没有填词的纯音乐，请您静候"))
show("empty", parse("   \n  "))
d = parse("[1000,4000](0,600,0)你(600,600,0)好")
out.write(f"idx@500 -> {d.index_at(500)}; idx@1300 -> {d.index_at(1300)}; idx@1700 -> {d.index_at(1700)}\n")
out.write(f"word_progress@1200 -> {d.word_progress(0,1200)}\n")
open("tools/_lyrics_out.txt","w",encoding="utf-8").write(out.getvalue())
print("ok")
