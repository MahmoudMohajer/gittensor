#!/usr/bin/env python3
"""
Fetch open PRs containing the Gittensor tagline to track competitors.
Uses GitHub Search API and calculates estimated scores using the real validator logic.
"""
import os
import sys
import sqlite3
from dotenv import load_dotenv

# Add project root to path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.append(project_root)

# Import service
from dashboard.services.competitor_service import fetch_gittensor_prs
from gittensor.validator.utils.load_weights import load_programming_language_weights, load_master_repo_weights

load_dotenv()

def get_token():
    token = os.environ.get("GITTENSOR_MINER_PAT")
    if not token:
        print("Error: GITTENSOR_MINER_PAT environment variable not set")
        sys.exit(1)
    return token

def init_db(db_path):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS prs (
            id TEXT PRIMARY KEY,
            repo TEXT,
            author TEXT,
            title TEXT,
            number INTEGER,
            url TEXT,
            created_at TEXT,
            updated_at TEXT,
            state TEXT,
            age INTEGER,
            additions INTEGER DEFAULT 0,
            deletions INTEGER DEFAULT 0,
            estimated_score REAL DEFAULT 0
        )
    ''')
    conn.commit()
    return conn

def main():
    token = get_token()
    
    print("Loading weights...")
    lang_weights = load_programming_language_weights()
    repo_weights = load_master_repo_weights()
    
    # Check if we are running from dashboard dir or project root
    if os.path.basename(os.getcwd()) == 'dashboard':
         db_path = 'opportunities.db'
    else:
         db_path = os.path.join(os.path.dirname(__file__), '../dashboard/opportunities.db')

    conn = init_db(db_path)
    
    count = fetch_gittensor_prs(token, conn, lang_weights, repo_weights)
    conn.close()
    
    print(f"Sync complete. {count} competitor PRs stored with estimated scores.")

if __name__ == "__main__":
    main()
