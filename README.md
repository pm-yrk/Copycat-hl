# copycat.hl no-lock npm fix

This patch changes both Dockerfiles to copy only `frontend/package.json` before `npm install`, avoiding Render's npm/package-lock failure. It also checks that `next` actually installed before build.
