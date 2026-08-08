import sqlite3
conn = sqlite3.connect('data/metadata.db')
c = conn.cursor()
c.execute("UPDATE files SET import_status='failed' WHERE import_status='processing'")
conn.commit()
print(f"已清理{c.rowcount}条processing记录")
conn.close()
