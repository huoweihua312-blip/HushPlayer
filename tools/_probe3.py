import os, sqlite3
p = os.path.abspath("artifacts/tmp_shots/data/hushplayer.db")
con = sqlite3.connect(p)
for row in con.execute("select name, cover_track_id, substr(coalesce(artwork_path,''),-40) from albums limit 5"):
    print("ALBUM", row)
for row in con.execute("select title, substr(coalesce(artwork_path,''),-40) from tracks limit 3"):
    print("TRACK", row)
print("artwork dir", len(os.listdir(os.path.abspath("artifacts/tmp_shots/data/cache/artwork"))))
