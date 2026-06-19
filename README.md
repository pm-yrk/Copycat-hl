# Copycat final polish patch

This patch updates the Copycat dashboard UI only.

Changes included:
- Makes "View all orders" a subtle text link instead of a filled button.
- Removes/hides the top data-quality card; footer remains the status source.
- Fixes USDC/CASH to use the USDC icon source.
- Removes synthetic token icon backgrounds so real token artwork appears cleanly.
- Converts asset signal board signal values from decimals to percentages.
- Fixes long/short exposure percentages to display long-share percentage only.
- Ensures exposure bars are calculated directly from long USD vs short USD and always fill 100%.
- Moves the exposure percentage away from the bar for readability.
- Refines the positioning-bias pill with a shorter premium brushed-metal slider.
- Adds a proper inline shield SVG for the disclaimer bar.
- Makes light-mode panels beige-on-beige with dark text.

Files changed:
- frontend/app/dashboard/page.tsx
- frontend/app/styles.css
