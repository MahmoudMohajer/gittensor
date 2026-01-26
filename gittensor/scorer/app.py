
import sys
import os
import asyncio
from flask import Flask, request, jsonify
from dataclasses import asdict
import bittensor as bt

# Add the project root to sys.path to allow importing gittensor modules
# Assuming this file is in gittensor/scorer/app.py and we want to import from gittensor/gittensor (package)
# The user's workspace structure is .../gittensor/gittensor -> root of repo
# So sys.path should include the root.
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR)) # Navigate up to project root if needed
# Actually, if runs from root, just current dir is enough.
# Let's assume we run from the root of the repo.
sys.path.append(os.getcwd())

from gittensor.classes import GitPatSynapse, MinerEvaluation
from gittensor.validator.evaluation.reward import reward
from gittensor.validator.utils.load_weights import load_master_repo_weights, load_programming_language_weights

app = Flask(__name__)

# Load weights once at startup
print("Loading weights...")
try:
    MASTER_REPOSITORIES = load_master_repo_weights()
    PROGRAMMING_LANGUAGES = load_programming_language_weights()
    print(f"Loaded {len(MASTER_REPOSITORIES)} repositories and {len(PROGRAMMING_LANGUAGES)} languages.")
except Exception as e:
    print(f"Error loading weights: {e}")
    MASTER_REPOSITORIES = {}
    PROGRAMMING_LANGUAGES = {}

# Mock Axon for GitPatSynapse
class MockAxon:
    def __init__(self, hotkey):
        self.hotkey = hotkey

@app.route('/score', methods=['POST'])
def score():
    data = request.json
    if not data or 'pat' not in data:
        return jsonify({"error": "Missing 'pat' in request body"}), 400

    pat = data['pat']
    uid = data.get('uid', 0)
    hotkey = data.get('hotkey', 'dummy_hotkey')

    # Create Mock Synapse
    synapse = GitPatSynapse(github_access_token=pat)
    # Inject mock axon
    synapse.axon = MockAxon(hotkey)

    # Run reward logic
    # Since reward is async, we need to run it in an event loop
    try:
        # Check if we can get a loop
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        miner_eval = loop.run_until_complete(
            reward(uid, synapse, MASTER_REPOSITORIES, PROGRAMMING_LANGUAGES)
        )
        
        # Serialize MinerEvaluation
        # MinerEvaluation is a dataclass, but contains other dataclasses (PullRequest, etc.)
        # We can use a custom serialization or asdict if fields are simple.
        # However, MinerEvaluation has complex fields.
        # Let's construct a response dict.
        
        response = {
            "uid": miner_eval.uid,
            "hotkey": miner_eval.hotkey,
            "github_id": miner_eval.github_id,
            "score": miner_eval.total_score,
            "base_score": miner_eval.base_total_score,
            "failed_reason": miner_eval.failed_reason,
            "pull_requests": []
        }
        
        for pr in miner_eval.pull_requests:
            pr_dict = {
                "number": pr.number,
                "repo": pr.repository_full_name,
                "base_score": pr.base_score,
                "earned_score": pr.earned_score,
                "lines_scored": pr.total_lines_scored,
                "issue_multiplier": pr.issue_multiplier,
            }
            response["pull_requests"].append(pr_dict)
            
        return jsonify(response)

    except Exception as e:
        app.logger.error(f"Error during scoring: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
