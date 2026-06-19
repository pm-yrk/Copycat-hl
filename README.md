# Copycat mobile/desktop fetch stability patch

This patch fixes the issue where opening the dashboard on mobile can make the desktop dashboard jump or show "Failed to fetch".

What changed:
- Frontend now requests one combined `/api/dashboard-feed` payload every second instead of 6+ separate API calls every second.
- Frontend prevents overlapping refreshes from the same tab.
- Frontend keeps the last good dashboard data on screen during tiny network blips instead of showing a visible error and moving the layout.
- Token logo lookups are cached and only requested when the token set changes.
- Backend serves a sub-second shared dashboard cache so desktop + mobile tabs do not overload the API/database.
- Backend CORS now accepts Render URLs and copycat.hl-style domains more safely.

Apply this patch, push to GitHub, let Render redeploy both API and frontend, then hard-refresh the dashboard on desktop and mobile.
