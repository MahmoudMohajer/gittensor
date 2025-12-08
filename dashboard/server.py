from flask import Flask, jsonify, request, send_from_directory
import sqlite3
import json
import os

app = Flask(__name__, static_url_path='', static_folder='.')

DB_PATH = os.path.join(os.path.dirname(__file__), 'opportunities.db')

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/style.css')
def style():
    return send_from_directory('.', 'style.css')

@app.route('/app.js')
def script():
    return send_from_directory('.', 'app.js')

@app.route('/api/issues')
def get_issues():
    min_age = request.args.get('min_age', default=0, type=int)
    max_age = request.args.get('max_age', default=99999, type=int)
    search = request.args.get('search', default='', type=str).lower()
    sort_by = request.args.get('sort', default='weight', type=str)
    difficulty = request.args.get('difficulty', default='', type=str)

    query = "SELECT * FROM issues WHERE age >= ? AND age <= ?"
    params = [min_age, max_age]

    if search:
        query += " AND (lower(repo) LIKE ? OR lower(title) LIKE ?)"
        params.extend([f'%{search}%', f'%{search}%'])

    if difficulty:
        query += " AND difficulty = ?"
        params.append(difficulty)

    if sort_by == 'age':
        query += " ORDER BY age DESC"
    elif sort_by == 'difficulty':
        # Custom sort for difficulty: Easy > Medium > Hard
        query += """ ORDER BY 
            CASE difficulty 
                WHEN 'Easy' THEN 3 
                WHEN 'Medium' THEN 2 
                WHEN 'Hard' THEN 1 
                ELSE 0 
            END DESC"""
    else: # Default weight
        query += " ORDER BY weight DESC"

    # Limit results purely for performance if UI doesn't paginae, but let's fetch all for now
    # query += " LIMIT 500" 

    conn = get_db_connection()
    issues = conn.execute(query, params).fetchall()
    conn.close()

    return jsonify({
        "issues": [dict(ix) for ix in issues],
        "count": len(issues)
    })

@app.route('/competitors')
def competitors():
    return send_from_directory('.', 'competitors.html')

@app.route('/competitors.js')
def competitors_script():
    return send_from_directory('.', 'competitors.js')

@app.route('/api/prs')
def get_prs():
    search = request.args.get('search', default='', type=str).lower()
    sort_by = request.args.get('sort', default='updated', type=str)

    query = "SELECT * FROM prs WHERE 1=1"
    params = []

    if search:
        query += " AND (lower(repo) LIKE ? OR lower(author) LIKE ? OR lower(title) LIKE ?)"
        params.extend([f'%{search}%', f'%{search}%', f'%{search}%'])

    if sort_by == 'age':
        query += " ORDER BY age DESC"
    elif sort_by == 'author':
        query += " ORDER BY author ASC"
    elif sort_by == 'score':
        query += " ORDER BY estimated_score DESC"
    else:  # Default: updated (most recent first)
        query += " ORDER BY updated_at DESC"

    conn = get_db_connection()
    try:
        prs = conn.execute(query, params).fetchall()
    except sqlite3.OperationalError:
        # Table doesn't exist yet
        prs = []
    conn.close()

    return jsonify({
        "prs": [dict(p) for p in prs],
        "count": len(prs)
    })

if __name__ == '__main__':
    print("Starting server on http://localhost:8000")
    app.run(port=8000, debug=True)
