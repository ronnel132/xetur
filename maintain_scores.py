import MySQLdb
import redis
import time
from datetime import datetime, timedelta
from math import log
from xetur import get_app

# Background process for maintaining the scores stored in redis, as per the 
# Reddit ranking algorithm. Designed to be run as a cron job. 

app = get_app()
r_server = redis.Redis(app.config['REDIS_HOST'], port=app.config['REDIS_PORT'], password=app.config['REDIS_PASS'])
epoch = datetime(1970, 1, 1)

def epoch_seconds(date):
    date = datetime.strptime(date, "%H:%M:%S %Y-%m-%d")
    td = date - epoch
    return td.days * 86400 + td.seconds 

def score(upvotes, downvotes):
    return upvotes - downvotes

def compute_score(upvotes, downvotes, date):
    s = score(upvotes, downvotes)
    order = log(max(abs(s), 1), 10)
    sign = 1 if s > 0 else -1 if s < 0 else 0
    seconds = epoch_seconds(date) - 1134028003
    return round(order + sign * seconds / 45000, 7)

def maintain_post_scores(topics):
    for topic in topics:
        post_ids = r_server.zrange(topic + ":posts", 0, -1) 
        for post_id in post_ids:
            upvotes = int(r_server.get("post:" + str(post_id) + ":upvotes"))
            downvotes = int(r_server.get("post:" + str(post_id) + ":downvotes"))
            date = r_server.get("post:" + str(post_id) + ":time")
            score = compute_score(upvotes, downvotes, date)
            r_server.zadd(topic + ":posts", post_id, score)
            r_server.zadd("all:posts", post_id, score)
   
def maintain_comment_scores():
    post_ids = r_server.zrange("all:posts", 0, -1)
    for post_id in post_ids:
        comment_ids = r_server.zrange(post_id + ":comments", 0, -1)
        for comment_id in comment_ids:
            upvotes = int(r_server.get("comment:" + str(comment_id) + ":upvotes"))
            downvotes = int(r_server.get("comment:" + str(comment_id) + ":downvotes"))
            date = r_server.get("comment:" + str(comment_id) + ":time")
            score = compute_score(upvotes, downvotes, date)
            r_server.zadd(str(post_id)+ ":comments", comment_id, score)

def maintain_scores():
    db = MySQLdb.connect(host=app.config['MYSQL_HOST'], user=app.config['MYSQL_USER'], \
    passwd=app.config['MYSQL_PASS'], db=app.config['MYSQL_DB'])
    cur = db.cursor()
    cur.execute('select * from topics')
    topics = cur.fetchall()
    cur.close()
    db.close()
    # each topic stored in a tuple like this: (topic,).
    topics = [topic[0] for topic in topics]
    maintain_post_scores(topics)
    maintain_comment_scores()

if __name__ == '__main__':
    maintain_scores()
