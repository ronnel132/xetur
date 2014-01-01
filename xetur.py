"""
    xetur 
    ~~~~~

    A reddit clone made with Flask, Redis and MySQL.
"""
import hashlib
import MySQLdb
import os
import random
import redis
import settings
import time
from contextlib import closing
from datetime import datetime
from flask import Flask, request, session, g, redirect, url_for, render_template, jsonify
from time import mktime

# Initialize the app and set our configuration
app = Flask(__name__)
app.config.from_object(settings)

# Connect to the redis server
r_server = redis.Redis(host=app.config['REDIS_HOST'], port=app.config['REDIS_PORT'], \
password=app.config['REDIS_PASS'])

def get_app():
    return app

def connect_db():
    return MySQLdb.connect(host=app.config['MYSQL_HOST'], user=app.config['MYSQL_USER'],\
        passwd=app.config['MYSQL_PASS'], db=app.config['MYSQL_DB'])

def query_db(query, args=(), one=False):
    g.cur.execute(query, args)
    return g.cur.fetchone() if one else g.cur.fetchall()

def order_topics(topics):
    topic_dict = {}
    for topic in topics:
        topic_dict[topic] = r_server.zcard(topic + ':posts')
    return sorted(topic_dict, key=topic_dict.get, reverse=True)

@app.before_request
def before_request():
    # open db connection before request
    g.db = connect_db()
    g.cur = g.db.cursor()
    g.username = None
    if 'username' in session:
        g.username = session['username']
    topics = query_db('select topic from topics')
    topics = order_topics([topic[0] for topic in topics])[:10]
    g.topics = topics

@app.teardown_request
def teardown_request(exception):
    # close db connection after request
    db = getattr(g, 'db', None)
    cur = getattr(g, 'cur', None)
    cur.close() if cur != None else None
    db.close() if db != None else None

# Parse posts into a list of dictionaries for easy access to post attributes
def parse_posts(posts):
    parsed = [dict(post_id=post[0], url=clean_url(post[1]), topic=post[2], poster=post[3], subject=post[4], \
    body=post[5], upvotes=r_server.get("post:" + str(post[0]) + ":upvotes"), \
    downvotes=r_server.get("post:" + str(post[0]) + ":downvotes"), \
    comment_count=r_server.zcard(str(post[0])+":comments")) for post in posts]
    return parsed

def parse_comments(comments):
    parsed = [dict(comment_id=cmnt[0], post_id=cmnt[1], poster=cmnt[2], body=cmnt[3], \
    upvotes=r_server.get("comment:"+str(cmnt[0])+":upvotes"), \
    downvotes=r_server.get("comment:"+str(cmnt[0])+":downvotes")) \
    for cmnt in comments]
    return parsed

# Fetch an individual post based on a unique post_id
def fetch_post(post_id):
    return query_db('select * from posts where post_id=%s', (post_id), True)

def fetch_comment(comment_id):
    return query_db('select * from comments where comment_id=%s', (comment_id), True)

def clean_url(url):
    return (url if 'http://' in url else 'http://' + url) if url != None else None

def parse_form(form):
    new_form = {}
    for v in form:
        new_form[v] = None if form[v] == "" else form[v]
    return new_form

def generate_salt():
    """Generate salt for secure password storage."""
    chars = []
    for i in range(8):
        chars.append(random.choice(app.config['ALPHABET']))
    return "".join(chars)

def password_hash(password, salt):
    salted_password = salt + password
    hashed = hashlib.sha256(salted_password).hexdigest()
    return hashed

def get_page(topic, before):
    if before == None:
        post_ids = r_server.zrevrange(topic + ':posts', 0, app.config['POSTS_PER_PAGE'] - 1)
        after = app.config['POSTS_PER_PAGE']
    else: 
        before = int(before)
        post_ids = r_server.zrevrange(topic + ':posts', before, before + app.config['POSTS_PER_PAGE'] - 1)
        after = before + app.config['POSTS_PER_PAGE']
    return after, post_ids

@app.route('/')
@app.route('/before=<before>')
def main_page(before=None):
    before, post_ids = get_page('all', before)
    has_next = before < r_server.zcard("all:posts")
    raw_posts = [fetch_post(post_id) for post_id in post_ids]
    posts = parse_posts(raw_posts) 
    return render_template('main_page.html', posts=posts, before=before, has_next=has_next,\
    posts_per_page=app.config['POSTS_PER_PAGE'])

# 'branches' are the equivalent of subreddits
@app.route('/x/<topic>')
@app.route('/x/<topic>/before=<before>')
def branch(topic, before=None):
    """Show a branch (topic), with posts ordered by score"""
    before, post_ids = get_page(topic, before)
    has_next = before < r_server.zcard(topic + ":posts")
    raw_posts = [fetch_post(post_id) for post_id in post_ids]
    posts = parse_posts(raw_posts)
    description = query_db('select description from topics where topic=%s', (topic), True)[0]
    return render_template('show_topic.html', topic=topic, posts=posts, before=before, \
    has_next=has_next, posts_per_page=app.config['POSTS_PER_PAGE'], description=description)

@app.route('/x/addbranch', methods=['GET', 'POST'])
def addbranch():
    """Create a branch"""
    if g.username == None:
        return redirect(url_for('login'))
    error = None
    if request.method == 'POST':
        bn = request.form['branch_name']
        bd = request.form['branch_descrip']
        if bn != "" or bd != "":
            query_db('insert into topics values (%s, %s)', (bn, bd))
            g.db.commit()
            return redirect(url_for('main_page'))
        error = "Branch must have a name and a description"
    return render_template('addbranch.html', error=error)

@app.route('/x/<topic>/<post_id>')
def show_post(topic, post_id):
    """Show a post and its associated comments, ordered by score."""
    comment_ids = r_server.zrevrange(post_id + ":comments", 0, -1)
    raw_comments = [fetch_comment(comment_id) for comment_id in comment_ids]
    comments = parse_comments(raw_comments)
    # parse_posts returns a singelton list in this case
    post = parse_posts([fetch_post(post_id)])[0]
    return render_template('show_post.html', comments=comments, post=post)

def redis_insert(insert_type, insert_id):
    now = datetime.now().strftime('%H:%M:%S %Y-%m-%d')
    r_server.set(insert_type + ':' + str(insert_id) + ':upvotes', 0)
    r_server.set(insert_type + ':' + str(insert_id) + ':downvotes', 0)
    r_server.set(insert_type + ':' + str(insert_id) + ':time', now)
        
@app.route('/x/<topic>/post', methods=['GET', 'POST'])
def post(topic):
    """Submit a post to a branch."""
    if g.username == None:
        return redirect(url_for('login')) 
    error = None
    form = parse_form(request.form)
    if request.method == 'POST':
        if form['subject'] != None:
            body = form['body']
            url = form['url']
            query_db('insert into posts (url, topic, poster, subject, body) values (%s, %s, %s, %s, %s)', \
                (url, topic, g.username, form['subject'], body))
            g.db.commit()
            post_id = query_db('select last_insert_id()', one=True)[0]
            r_server.zadd(topic + ":posts", post_id, 0)
            redis_insert('post', post_id)
            r_server.zadd("all:posts", post_id, 0)
            return redirect(url_for('show_post', topic=topic, post_id=post_id))
        error = "Invalid Post: Posts Must have Subject and Body" 
    return render_template('post.html', topic=topic, error=error)

@app.route('/comment', methods=['POST'])
def comment():
    """URL for handling when a user comments."""
    if g.username == None:
        return jsonify ({
            'authorized' : False })
    elif request.form['text'] != "":
        post_id = request.form['post_id']
        body = request.form['text']
        query_db('insert into comments (post_id, poster, body) values (%s, %s, %s)', \
        (post_id, g.username, body))
        g.db.commit()
        comment_id = query_db('select last_insert_id()', one=True)[0]
        r_server.zadd(str(post_id) + ":comments", comment_id, 0)
        redis_insert('comment', comment_id)
        return jsonify ({ 
            'authorized' : True,
            'success' : True,
            'comment_id' : comment_id,
            'username': session['username'] })
    else:
        return jsonify ({
            'authorized' : True,
            'success' : False })

@app.route('/upvote', methods=['POST'])
def upvote():
    """URL for handling upvoting posts or comments."""
    id = str(request.form['id'])
    # a vote_type may be either 'comment' or 'post'
    vote_type = request.form['type']
    r_server.incr(vote_type + ":" + id + ":upvotes")
    return jsonify({
        'upvotes' : r_server.get(vote_type + ":" + id + ":upvotes") })

@app.route('/downvote', methods=['POST'])
def downvote():
    """URL for handling downvoting posts or comments."""
    id = str(request.form['id'])
    vote_type = request.form['type']
    r_server.incr(vote_type + ":" + id + ":downvotes")
    return jsonify({
        'downvotes' : r_server.get(vote_type + ":" + id + ":downvotes") })

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login a user."""
    if g.username != None:
        return redirect(url_for('main_page'))
    error = None
    if request.method == 'POST':
        user_details = query_db('select * from users where username=%s', \
            (request.form['username']), True)
        if user_details != None:
            salt = user_details[1]
            pass_hash = user_details[2]
            if password_hash(request.form['password'], salt) == pass_hash:
                session['username'] = user_details[0]
                return redirect(url_for('main_page'))
        error = "Username or Password Invalid"
    return render_template('login.html', error=error)

@app.route('/register', methods=['GET', 'POST'])
def register():
    """Register a new user."""
    # user is already logged in!
    if g.username != None:
        return redirect(url_for('main_page'))
    error = None
    if request.method == 'POST':
        # register the user
        username = request.form['username']
        username_exisits = query_db('select %s in (select username from users)', (username), True)[0]
        if username_exists:
            error = "Username already in use"
        elif len(username) > 25:
            error = "Username is too long"
        else:
            # Username is valid
            if request.form['password'] != request.form['confirm_password']:
                error = "Invalid password"
            elif len(password) < 6:
                error = "Password must be at least 6 characters"
            else:
                salt = generate_salt()
                hashed = password_hash(password, salt)
                query_db('insert into users (username, salt, password_hash) values (%s, %s, %s)', \
                    (username, salt, hashed))
                g.db.commit()
                return redirect(url_for('login'))
    return render_template('register.html', error=error)

@app.route('/logout')
def logout():
    """Logout a user."""
    session.pop('username', None)
    return redirect(url_for('main_page'))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, threaded=True)

