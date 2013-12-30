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
from sys import maxint
from time import mktime

# Initialize the app and set our configuration
app = Flask(__name__)
app.config.from_object(settings)

# Connect to the redis server
r_server = redis.Redis(host=app.config['REDIS_HOST'], port=app.config['REDIS_PORT'], password=app.config['REDIS_PASS'])

def get_app():
    return app

def connect_db():
    return MySQLdb.connect(host=app.config['MYSQL_HOST'], user=app.config['MYSQL_USER'],\
        passwd=app.config['MYSQL_PASS'], db=app.config['MYSQL_DB'])

@app.before_request
def before_request():
    # open db connection before request
    g.db = connect_db()
    g.cur = g.db.cursor()
    g.username = None
    if 'username' in session:
        g.username = session['username']
    g.cur.execute('select topic from topics')
    topics = [topic[0] for topic in g.cur.fetchall()]
    g.topics = topics

@app.teardown_request
def teardown_request(exception):
    # close db connection after request
    db = getattr(g, 'db', None)
    cur = getattr(g, 'cur', None)
    if cur != None:
        cur.close()
    if db != None:
        db.close()

# Parse posts into a list of dictionaries for easy access to post attributes
def parse_posts(posts):
    parsed = [dict(post_id=post[0], url=clean_url(post[1]), topic=post[2], poster=post[3], subject=post[4], \
    body=post[5], upvotes=r_server.get("post:" + str(post[0]) + ":upvotes"), \
    downvotes=r_server.get("post:" + str(post[0]) + ":downvotes"), \
    comment_count=r_server.zcount(str(post[0])+":comments",-maxint,maxint))\
    for post in posts]
    return parsed

def parse_comments(comments):
    parsed = [dict(comment_id=cmnt[0], post_id=cmnt[1], poster=cmnt[2], body=cmnt[3], \
    upvotes=r_server.get("comment:"+str(cmnt[0])+":upvotes"), \
    downvotes=r_server.get("comment:"+str(cmnt[0])+":downvotes")) \
    for cmnt in comments]
    return parsed

# Fetch an individual post based on a unique post_id
def fetch_post(post_id):
    g.cur.execute('select * from posts where post_id=%s', [int(post_id)])
    return g.cur.fetchone()

def fetch_comment(comment_id):
    g.cur.execute('select * from comments where comment_id=%s', [int(comment_id)])
    return g.cur.fetchone()

def clean_url(url):
    if url is None:
        return None
    elif 'http://' not in url:
        url = 'http://' + url
    return url

@app.route('/')
@app.route('/before=<before>')
def main_page(before=None):
    if before == None:
        post_ids = r_server.zrevrange('all:posts', 0, app.config['POSTS_PER_PAGE'] - 1)
        before = app.config['POSTS_PER_PAGE']
    else:
        post_ids = r_server.zrevrange('all:posts', int(before), int(before) + app.config['POSTS_PER_PAGE'] - 1)
        before = int(before) + app.config['POSTS_PER_PAGE']
    has_next = before < r_server.zcount("all:posts", -maxint, maxint)
    raw_posts = [fetch_post(post_id) for post_id in post_ids]
    posts = parse_posts(raw_posts) 
    return render_template('main_page.html', posts=posts, before=before, has_next=has_next,\
    posts_per_page=app.config['POSTS_PER_PAGE'])

# 'branches' are the equivalent of subreddits
@app.route('/x/<topic>')
@app.route('/x/<topic>/before=<before>')
def branch(topic, before=None):
    """Show a branch (topic), with posts ordered by score"""
    if before == None:
        post_ids = r_server.zrevrange(topic + ":posts", 0, app.config['POSTS_PER_PAGE'] - 1)
        before = app.config['POSTS_PER_PAGE']
    else:
        post_ids = r_server.zrevrange(topic + ':posts', int(before), int(before) + app.config['POSTS_PER_PAGE'] - 1)
        before = int(before) + app.config['POSTS_PER_PAGE']
    has_next = before < r_server.zcount(topic + ":posts", -maxint, maxint)
    raw_posts = [fetch_post(post_id) for post_id in post_ids]
    posts = parse_posts(raw_posts)
    return render_template('show_topic.html', topic=topic, posts=posts, before=before, \
    has_next=has_next, posts_per_page=app.config['POSTS_PER_PAGE'])

@app.route('/x/<topic>/<post_id>')
def show_post(topic, post_id):
    """Show a post and its associated comments, ordered by score."""
    comment_ids = r_server.zrevrange(post_id + ":comments", 0, -1)
    raw_comments = [fetch_comment(comment_id) for comment_id in comment_ids]
    comments = parse_comments(raw_comments)
    # parse_posts returns a singelton list in this case
    post = parse_posts([fetch_post(post_id)])[0]
    return render_template('show_post.html', comments=comments, post=post)

@app.route('/comment', methods=['POST'])
def comment():
    """URL for handling when a user comments."""
    if g.username == None:
        return jsonify ({
            'authorized' : False })
    elif request.form['text'] != "":
        post_id = request.form['post_id']
        body = request.form['text']
        g.cur.execute('insert into comments (post_id, poster, body) values (%s, %s, %s)', \
        [post_id, session['username'], body])
        g.db.commit()
        g.cur.execute('select last_insert_id()')
        comment_id = g.cur.fetchone()[0]
        r_server.zadd(str(post_id) + ":comments", comment_id, 0)
        r_server.set("comment:" + str(comment_id) + ":upvotes", 0)
        r_server.set("comment:" + str(comment_id) + ":downvotes", 0)
        r_server.set("comment:" + str(comment_id) + ":time", datetime.now().strftime("%H:%M:%S %Y-%m-%s"))
        return jsonify ({ 
            'authorized' : True,
            'success' : True,
            'comment_id' : comment_id,
            'username': session['username'] })
    else:
        return jsonify ({
            'authorized' : True,
            'success' : False })
        
@app.route('/x/<topic>/post', methods=['GET', 'POST'])
def post(topic):
    """Submit a post to a branch."""
    if g.username == None:
        return redirect(url_for('login')) 
    error = None
    if request.method == 'POST':
        if request.form['subject'] != "":
            body = request.form['body']
            body = body if body != "" else None
            url = request.form['url']
            url = url if url != "" else None

            g.cur.execute('insert into posts (url, topic, poster, subject, body) values (%s, %s, %s, %s, %s)', \
            [url, topic, session['username'], request.form['subject'], body])
            g.db.commit()
            
            # Get the post_id of the new post to use as a redis key
            g.cur.execute('select last_insert_id()')
            post_id = g.cur.fetchone()[0]
            # Initial score is 0
            r_server.zadd(topic + ":posts", post_id, 0)
            # Initial number of upvotes and downvotes is zero 
            r_server.set("post:" + str(post_id) + ":upvotes", 0)
            r_server.set("post:" + str(post_id) + ":downvotes", 0)
            # Time of post is now
            r_server.set("post:" + str(post_id) + ":time", datetime.now().strftime("%H:%M:%S %Y-%m-%d"))
            # Store this post and it's score in the all:posts ordered list for fast front-page loads
            r_server.zadd("all:posts", post_id, 0)

            return redirect(url_for('branch', topic=topic))
        error = "Invalid Post: Posts Must have Subject and Body" 
    return render_template('post.html', topic=topic, error=error)

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

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login a user."""
    # user is already logged in!
    if g.username != None:
        return redirect(url_for('main_page'))
    error = None
    if request.method == 'POST':
        g.cur.execute('select * from users where username = %s', \
            [request.form['username']])
        raw_user_details = g.cur.fetchone()
        if raw_user_details != None:
            salt = raw_user_details[1]
            stored_password_hash = raw_user_details[2]
            if password_hash(request.form['password'], salt) == stored_password_hash:
                session['username'] = raw_user_details[0]
                g.cur.execute('select * from users')
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
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        username_exists = g.cur.execute('select %s in (select username from users)', [username])
        username_exists = g.cur.fetchone()[0]
        if username_exists:
            error = "Username already in use"
        elif len(username) > 25:
            error = "Username is too long"
        else:
            # Username is valid
            if password != confirm_password:
                error = "Invalid password"
            elif len(password) < 6:
                error = "Password must be at least 6 characters"
            else:
                salt = generate_salt()
                hashed_password = password_hash(password, salt)
                g.cur.execute('insert into users (username, salt, password_hash) values (%s, %s, %s)', [username, salt, hashed_password])
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

