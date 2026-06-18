FROM node:20-bookworm-slim
WORKDIR /app

# Render builds were hitting an npm/lockfile failure. Avoid package-lock during Docker install
# and verify Next.js was actually installed before trying to build.
ENV NPM_CONFIG_AUDIT=false \
    NPM_CONFIG_FUND=false \
    NPM_CONFIG_UPDATE_NOTIFIER=false

COPY frontend/package.json ./
RUN npm install --no-package-lock --no-audit --no-fund --legacy-peer-deps && test -x ./node_modules/.bin/next

COPY frontend ./

# Safe build-time placeholders. Real values are read at runtime through
# /api/runtime-config from Render environment variables.
ENV NEXT_PUBLIC_SUPABASE_URL=https://placeholder.supabase.co
ENV NEXT_PUBLIC_SUPABASE_ANON_KEY=placeholder-build-key
ENV NEXT_PUBLIC_API_BASE_URL=https://hwt-api.onrender.com

RUN npm run build
CMD ["npm", "run", "start"]
