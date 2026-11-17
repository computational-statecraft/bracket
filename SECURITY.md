# Security

Please report security problems privately, through this repository's **Security** tab → **Report a vulnerability**
(GitHub's private vulnerability reporting), not in a public issue.

Useful to know when reporting:

- [bracket] serves its page only on `127.0.0.1` (the local computer). Requests from other sites are refused: the
  server checks the `Host` header, requires an `X-Bracket` header on every change, and rejects cross-site requests.
- Nothing leaves the computer unless the optional Claude tier is switched on with an Anthropic API key; then only the
  sentence being worked on is sent. The key is stored in the per-user settings file, never in the repository.
- Model files are downloaded from Hugging Face at pinned revisions and checked against a SHA-256 before use.
