import os, sqlite3
p = os.path.abspath("artifacts/tmp_shots/data/hushplayer.db")
con = sqlite3.connect(p)
print([r[0] for r in con.execute("select name from sqlite_master where type='table'")])
print("size", os.path.getsize(p))
