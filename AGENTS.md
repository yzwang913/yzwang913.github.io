# AGENTS.md

## Repo Purpose

This repository is the GitHub Pages landing site for the MR HT Lattice Viewer project.

It is not the main application backend. This repo mainly contains:

- the public landing page shown at `https://yzwang913.github.io/`
- the password-gated project entry in `index.html`
- `tunnel_keeper.py`, which keeps Cloudflare Quick Tunnel links fresh and writes them back into `index.html`

## Key Files

- `index.html`
  - public landing page
  - contains the "打开项目" and "在页面内预览" buttons
  - contains the frontend password gate for project access
- `tunnel_keeper.py`
  - starts Cloudflare Quick Tunnels for local ports
  - extracts new `trycloudflare.com` URLs from `cloudflared`
  - updates `index.html`
  - can commit and push `index.html`

## Important Architecture

The actual Flask app is not in this repo.

Current backend location:

- `/data/work/yzwang/calculation/MR_HT_web_show/web_show/app.py`

That means:

- if the landing page UI is wrong, edit this repo
- if the project page itself is wrong, the real app is likely in `/data/work/.../web_show/`
- do not assume everything is versioned in this GitHub Pages repo

## Current Port Mapping

Managed by `tunnel_keeper.py`:

- `nano` -> `127.0.0.1:1999`
- `band` -> `127.0.0.1:7002`

## Password Gate

The landing page currently uses a frontend password gate.

Known current password for the `nano` project:

- `5002`

The hash is stored in `index.html`, not the plaintext.

## Local vs Public Access

`index.html` may contain both:

- public `trycloudflare` links for outside access
- runtime override logic that prefers `http://127.0.0.1:1999/` when opened locally on the cluster/login node

This is intentional.

When checking behavior, distinguish between:

- opening `https://yzwang913.github.io/` from an external browser
- opening the local file/page on the cluster side

## How The Public Link Is Refreshed

Typical flow:

1. Flask app runs on login node at `127.0.0.1:1999`.
2. `tunnel_keeper.py` starts `cloudflared tunnel --url http://127.0.0.1:1999`.
3. `tunnel_keeper.py` updates `index.html` with the newest public link.
4. It may commit and push `index.html` automatically.

If the public page opens but the project link is dead, check:

- whether `app.py` is still running
- whether `cloudflared` is still running
- whether `tunnel_keeper.py` updated `index.html`

## Files That Should Usually Not Be Committed

These are runtime artifacts, not source files:

- `nohup.out`
- `id.txt`
- `__pycache__/`

Do not include them in commits unless explicitly requested.

## Practical Editing Guidance For Future AI

- Read `index.html` first if the user reports button, password, preview, or landing-page issues.
- Read `tunnel_keeper.py` first if the user reports stale public links or cluster/local access issues.
- If the issue is inside the opened project page, inspect `/data/work/yzwang/calculation/MR_HT_web_show/web_show/app.py` instead of assuming this repo contains the backend.
- Be careful with auto-push logic in `tunnel_keeper.py`; it can race with manual edits to `index.html`.
- Prefer committing only intentional source changes.

## Verification Tips

Useful checks:

- open `https://yzwang913.github.io/`
- click "打开项目"
- enter password `5002`
- confirm the new tab opens the project page successfully
- verify the target tunnel returns HTTP 200

## Current Note

This repo is used as an operational bridge between a public GitHub Pages entry page and a backend that actually lives elsewhere on the cluster.
