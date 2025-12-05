from flask import Flask, jsonify, request
import requests

app = Flask(__name__)

GITHUB_API_BASE = "https://api.github.com"
TIMEOUT_SECONDS = 5

# Simple in-memory cache:
# {
#   "users": { "username": { ...user_data... } },
#   "repos": { "username": [ ...list_of_repos... ] }
# }
CACHE = {
    "users": {},
    "repos": {}
}


def fetch_from_github(url):
    """
    Helper function to fetch data from GitHub with error handling.
    """
    try:
        resp = requests.get(url, timeout=TIMEOUT_SECONDS)
        # Raise for non-2xx
        resp.raise_for_status()
        data = resp.json()

        # Basic validation – ensure we at least have JSON/dict/list
        if not isinstance(data, (dict, list)):
            raise ValueError("Malformed JSON data from GitHub")

        return data, None
    except requests.exceptions.Timeout:
        return None, {"error": "Request to GitHub timed out", "code": "TIMEOUT"}
    except requests.exceptions.HTTPError:
        return None, {
            "error": "GitHub returned an error",
            "status_code": resp.status_code,
            "details": resp.text[:200]
        }
    except Exception as e:
        return None, {"error": "Network or parsing error", "details": str(e)}


def get_user(username):
    """
    Get GitHub user, using cache if possible.
    """
    username = username.lower()

    if username in CACHE["users"]:
        print("CACHE HIT: users", username)
        return CACHE["users"][username], None

    url = f"{GITHUB_API_BASE}/users/{username}"
    data, err = fetch_from_github(url)
    if err:
        return None, err

    # Basic field sanity check
    if "login" not in data:
        return None, {"error": "Malformed user data from GitHub"}

    CACHE["users"][username] = data
    return data, None


def get_repos(username):
    """
    Get GitHub repos for a user, using cache if possible.
    """
    username = username.lower()

    if username in CACHE["repos"]:
        print("CACHE HIT: repos", username)
        return CACHE["repos"][username], None


    url = f"{GITHUB_API_BASE}/users/{username}/repos"
    data, err = fetch_from_github(url)
    if err:
        return None, err

    if not isinstance(data, list):
        return None, {"error": "Malformed repo list from GitHub"}

    # Optional: keep only relevant fields to simplify output
    cleaned = []
    for repo in data:
        cleaned.append({
            "id": repo.get("id"),
            "name": repo.get("name"),
            "full_name": repo.get("full_name"),
            "html_url": repo.get("html_url"),
            "description": repo.get("description"),
            "language": repo.get("language"),
            "stargazers_count": repo.get("stargazers_count", 0),
            "forks_count": repo.get("forks_count", 0)
        })

    CACHE["repos"][username] = cleaned
    return cleaned, None


@app.route("/api/users/<username>", methods=["GET"])
def api_get_user(username):
    """
    Simple endpoint: return basic user info.
    Uses GitHub /users/{username} endpoint.
    """
    user, err = get_user(username)
    if err:
        return jsonify(err), 502  # Bad gateway (error from upstream API)

    # Return only some fields to keep it clean
    result = {
        "login": user.get("login"),
        "name": user.get("name"),
        "public_repos": user.get("public_repos"),
        "followers": user.get("followers"),
        "following": user.get("following"),
        "html_url": user.get("html_url"),
        "bio": user.get("bio"),
    }
    return jsonify(result), 200


@app.route("/api/users/<username>/repos", methods=["GET"])
def api_list_repos(username):
    """
    List repositories for a user, with optional filters:
      - language (exact match, case-insensitive)
      - min_stars (integer)
    Uses GitHub /users/{username}/repos endpoint.
    """
    repos, err = get_repos(username)
    if err:
        return jsonify(err), 502

    language = request.args.get("language", "").strip().lower()
    min_stars = request.args.get("min_stars", "").strip()

    try:
        min_stars = int(min_stars) if min_stars else None
    except ValueError:
        return jsonify({"error": "min_stars must be an integer"}), 400

    filtered = repos

    if language:
        filtered = [
            r for r in filtered
            if (r.get("language") or "").lower() == language
        ]

    if min_stars is not None:
        filtered = [
            r for r in filtered
            if (r.get("stargazers_count") or 0) >= min_stars
        ]

    return jsonify({
        "count": len(filtered),
        "items": filtered
    }), 200


@app.route("/api/users/<username>/repos/<int:repo_id>", methods=["GET"])
def api_repo_detail(username, repo_id):
    """
    Show detailed info for a single repository by its ID.
    We use the cached repo list for this user and find by 'id'.
    """
    repos, err = get_repos(username)
    if err:
        return jsonify(err), 502

    repo = next((r for r in repos if r.get("id") == repo_id), None)
    if not repo:
        return jsonify({"error": "Repository not found"}), 404

    # In a real app, you might call GitHub's single-repo endpoint here.
    # For the assignment, using cached list is fine.
    return jsonify(repo), 200


@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Endpoint not found"}), 404


@app.errorhandler(500)
def internal_error(e):
    return jsonify({"error": "Internal server error"}), 500


if __name__ == "__main__":
    # For local development
    app.run(debug=True)
