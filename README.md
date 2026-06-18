# copycat.hl force frontend Dockerfile fix

This patch adds the same fixed frontend Dockerfile at BOTH:

- `Dockerfile` at the repo root
- `frontend/Dockerfile`

This removes ambiguity if Render is accidentally building from the repo-root Dockerfile instead of `frontend/Dockerfile`.
