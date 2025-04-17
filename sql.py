import sqlite3

conn = sqlite3.connect('db/user.db')

cursor = conn.cursor()

# 创建表（如果表不存在）
cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    password TEXT NOT NULL
)
''')

# 插入数据（明文存储）
cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", ('huangchangfei', '123456'))

# 提交事务
conn.commit()

# 查询数据并打印结果
cursor.execute("SELECT * FROM users")
rows = cursor.fetchall()
for row in rows:
    print(f"ID: {row[0]}, Username: {row[1]}, Password: {row[2]}")

# 关闭连接
conn.close()
