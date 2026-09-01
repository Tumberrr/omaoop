import sqlite3

db = sqlite3.connect('db/exp.db')

c = db.cursor()

c.execute("""CREATE TABLE IF NOT EXISTS experience (
    user_id text PRIMARY KEY,
    user_name text,
    experience integer DEFAULT 0,
    rank text DEFAULT 'Без ранга'
)""")



c.execute("""CREATE TABLE IF NOT EXISTS experience_telegram (
    user_id text PRIMARY KEY,
    user_name text,
    experience integer DEFAULT 0,
    rank text DEFAULT 'Без ранга'
)""")



db.commit()
db.close()

def which_rank(user_id):
    db = sqlite3.connect('db/exp.db')
    c = db.cursor()
    c.execute("SELECT experience FROM EXPERIENCE where user_id = ? LIMIT 1", (user_id,))
    amount_exp = c.fetchone()
    if amount_exp[0] > 120: c.execute("UPDATE EXPERIENCE SET rank = 'Повелитель' WHERE user_id = ?", (user_id,))

    db.commit()
    db.close()

def which_rank_telegram(user_id):
    db = sqlite3.connect('db/exp.db')
    c = db.cursor()
    
    c.execute("SELECT experience FROM EXPERIENCE_TELEGRAM where user_id = ? LIMIT 1", (user_id,))
    amount_exp_telegram = c.fetchone()
    if amount_exp_telegram[0] > 18: c.execute("UPDATE EXPERIENCE_TELEGRAM SET rank = 'Повелитель' WHERE user_id = ?", (user_id,))

    db.commit()
    db.close()


def add_exp(user_id, user_name, experience):
    db = sqlite3.connect('db/exp.db')
    c = db.cursor()
    c.execute("SELECT 1 FROM experience WHERE user_id = ? LIMIT 1", (user_id,))
    result = c.fetchone()

    if result:
        print('Данный айди уже в базе данных')


    c.execute("""
        INSERT INTO experience (user_id, user_name, experience)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id)
        DO UPDATE SET
            experience = experience + excluded.experience,
            user_name = excluded.user_name
    """, (user_id, user_name, experience))

    c.execute("SELECT * FROM experience")
    print(c.fetchall())


    db.commit()
    db.close()

