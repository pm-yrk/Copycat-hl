FROM node:20-bookworm-slim
WORKDIR /app

ENV NPM_CONFIG_AUDIT=false \
    NPM_CONFIG_FUND=false \
    NPM_CONFIG_UPDATE_NOTIFIER=false

COPY frontend/package*.json ./
RUN rm -f package-lock.json npm-shrinkwrap.json && npm install --no-audit --no-fund --legacy-peer-deps --no-package-lock && npm cache clean --force

COPY frontend ./

ENV NEXT_PUBLIC_SUPABASE_URL=https://placeholder.supabase.co
ENV NEXT_PUBLIC_SUPABASE_ANON_KEY=placeholder-build-key
ENV NEXT_PUBLIC_API_BASE_URL=https://hwt-api.onrender.com

RUN test -x node_modules/.bin/next && npm run build
CMD ["npm", "run", "start"]
