import hashlib
import random
import redis
import settings
import sqlite3
import time
from contextlib import closing
from datetime import datetime
from flask import Flask, request, session, g, redirect, url_for, abort, render_template
from time import mktime

# Initialize the app and set our configuration
app = Flask(__name__)
app.config.from_object(settings)

# Connect to the redis server
r_server = redis.Redis(app.config['REDIS_HOST'], port=app.config['REDIS_PORT'])

def get_app():
    return app

def connect_db():
    return sqlite3.connect(app.config['DATABASE'])

# Initialize the sqlite database 
def init_db():
    with closing(connect_db()) as db:
        with app.open_resource('schema.sql', mode='r') as f:
            db.cursor().executescript(f.read())
        db.commit()

@app.before_request
def before_request():
    # open db connection before request
    g.db = connect_db()
    g.username = None
    if 'username' in session:
        g.username = session['username']
    topics = g.db.execute('select topic from topics').fetchall()
    topics = [topic[0] for topic in topics]
    g.topics = topics

@app.teardown_request
def teardown_request(exception):
    # close db connection after request
    db = getattr(g, 'db', None)
    if db != None:
        db.close()

# Parse posts into a list of dictionaries for easy access to post attributes
def parse_posts(posts):
    parsed = [dict(post_id=post[0], topic=post[1], poster=post[2], \
    subject=post[3], body=post[4], upvotes=r_server.get(str(post[0]) + ":upvotes"),
    downvotes=r_server.get(str(post[0]) + ":downvotes")) for post in posts]
    return parsed

# Fetch an individual post based on a unique post_id
def fetch_post(post_id):
    post = g.db.execute('select * from posts where post_id = ?', [int(post_id)]).fetchone()
    return post

@app.route('/')
def main_page():
    post_ids = r_server.zrevrange('all:posts', 0, app.config['POSTS_PER_PAGE'] - 1)
    raw_posts = [fetch_post(post_id) for post_id in post_ids]
    posts = parse_posts(raw_posts) 
    return render_template('main_page.html', posts=posts)

def parse_time(timestamp):
    seconds = mktime(datetime.strptime(date, "%Y-%m-%d %H:%M:%S").timetuple())
    return datetime.fromtimestamp(seconds)

# 'branches' are the equivalent of subreddits
@app.route('/x/<topic>')
def branch(topic):
    post_ids = r_server.zrange(topic + ":posts", 0, app.config['POSTS_PER_PAGE'] - 1)
    raw_posts = [fetch_post(post_id) for post_id in post_ids]
    posts = parse_posts(raw_posts)
    return render_template('show_topic.html', topic=topic, posts=posts)

@app.route('/x/<topic>/<post_id>')
def show_post(topic, post_id):
    cur1 = g.db.execute('select * from comments where post_id=?', [post_id])
    cur2 = g.db.execute('select * from posts where post_id=?', [post_id])
    comments = [dict(comment_id=row[0], post_id=row[1], poster=row[2], \
    body=row[3], upvotes=int(row[4]), downvotes=int(row[5]), posted_at=parse_time(row[6])) for row in cur1.fetchall()]
    post = parse_posts(cur2.fetchall())[0]
    return render_template('show_post.html', topic=topic, comments=comments, post=post)

@app.route('/x/<topic>/<post_id>/comment', methods=['POST'])
def comment(topic, post_id):
    if g.username == None:
        abort(401)
    if request.form['text'] != "":
        g.db.execute('insert into comments (post_id, poster, body) values (?, ?, ?)', \
        [post_id, session['username'], request.form['text']])
        g.db.commit()
    return redirect(url_for('show_post', topic=topic, post_id=post_id))

@app.route('/x/<topic>/post', methods=['GET', 'POST'])
def post(topic):
    if g.username == None:
        abort(401)
    error = None
    if request.method == 'POST':
        if request.form['subject'] != "" and request.form['body'] != "":
            g.db.execute('insert into posts (topic, poster, subject, body) values (?, ?, ?, ?)', \
            [topic, session['username'], request.form['subject'], request.form['body']])
            g.db.commit()
            
            # Get the post_id of the new post to use as a redis key
            post_id = g.db.execute('select last_insert_rowid()').fetchone()[0]

            # Initial score is 0
            r_server.zadd(topic + ":posts", post_id, 0)
            # Initial number of upvotes and downvotes is zero 
            r_server.set(str(post_id) + ":upvotes", 0)
            r_server.set(str(post_id) + ":downvotes", 0)
            # Time of post is now
            r_server.set(str(post_id) + ":time", datetime.now().strftime("%H:%M:%S %Y-%m-%d"))
            # Store this post and it's score in the all:posts ordered list for fast front-page loads
            r_server.zadd("all:posts", post_id, 0)

            return redirect(url_for('branch', topic=topic))
        error = "Invalid Post: Posts Must have Subject and Body" 
    return render_template('post.html', topic=topic, error=error)

def generate_salt():
    chars = []
    for i in range(8):
        chars.append(random.choice(app.config['ALPHABET']))
    return "".join(chars)

def password_hash(password, salt):
    salted_password = salt + password
    hashed = hashlib.sha256(salted_password).hexdigest()
    return hashed

@app.route('/login', methods=['GET', 'POST'])
def login():
    # user is already logged in!
    if g.username != None:
        return redirect(url_for('main_page'))
    error = None
    if request.method == 'POST':
        cur = g.db.execute('select * from users where username = ?', \
            [request.form['username']])
        raw_user_details = cur.fetchone()
        if raw_user_details != None:
            salt = raw_user_details[1]
            stored_password_hash = raw_user_details[2]
            if password_hash(request.form['password'], salt) == stored_password_hash:
                session['username'] = raw_user_details[0]
                return redirect(url_for('main_page'))
        error = "Username or Password Invalid"
    return render_template('login.html', error=error)

@app.route('/register', methods=['GET', 'POST'])
def register():
    # user is already logged in!
    if g.username != None:
        return redirect(url_for('main_page'))
    error = None
    if request.method == 'POST':
        # register the user
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        username_exists = g.db.execute('select ? in (select username from users)', [username]).fetchone()[0]
        if username_exists:
            error = "Username already in use"
        else:
            # Username is valid
            if password != confirm_password:
                error = "Invalid password"
            elif len(password) < 6:
                error = "Password must be at least 6 characters"
            else:
                salt = generate_salt()
                hashed_password = password_hash(password, salt)
                g.db.execute('insert into users (username, salt, password_hash) values (?, ?, ?)', [username, salt, hashed_password])
                g.db.commit()
                return redirect(url_for('login'))
    return render_template('register.html', error=error)

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('main_page'))

if __name__ == '__main__':
    app.run(threaded=True)

