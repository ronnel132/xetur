xetur
=====
A reddit clone implemented in Flask.

To run this reddit clone, type the following into your terminal:

1. `python -c "import xetur; xetur.init_db()"`
2. `python xetur.py`

Make sure you have a Redis server running on localhost, and the appropriate Python dependencies installed: `redis`, `sqlite3`, and `flask`. 

Then, navigate to "http://localhost:5000/" in your browser.
