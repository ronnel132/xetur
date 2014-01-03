import MySQLdb
import redis
from xetur import get_app

app = get_app()

db = MySQLdb.connect(host=app.config['MYSQL_HOST'], user=app.config['MYSQL_USER'], \
passwd=app.config['MYSQL_PASS'], db=app.config['MYSQL_DB'])

lines = open('schema.sql', 'r').readlines()
lines = [line.strip('\n') for line in lines]
filtered = []
for line in lines:
    if line != "":
        filtered.append(line)

commands =  "".join(filtered).split(';')[:-1]
cur = db.cursor()
for c in commands:
    cur.execute(c)

db.commit()
cur.close()
db.close()


# Also delete redis keys

r = redis.Redis(host=app.config['REDIS_HOST'], port=app.config['REDIS_PORT'], password=app.config['REDIS_PASS'])
r.flushdb()
r.flushall()
