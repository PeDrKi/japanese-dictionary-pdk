import sqlite3
conn = sqlite3.connect("database/japanese.db")
conn.execute("DELETE FROM sqlite_sequence WHERE name='cards'")
conn.commit()
conn.close()
print("done")
