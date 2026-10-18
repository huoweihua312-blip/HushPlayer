import os, sys, sqlite3
sys.path.insert(0, ".")
db = os.path.abspath("artifacts/tmp_shots/data")
print("db exists", os.path.isdir(db), os.listdir(db)[:8])
p = os.path.join(db, "library.db")
print("libdb", os.path.exists(p))
if os.path.exists(p):
    con = sqlite3.connect(p)
    for row in con.execute("select name, cover_track_id, artwork_path from albums limit 5"):
        print(row)
    for row in con.execute("select title, artwork_path from tracks limit 3"):
        print(row)
