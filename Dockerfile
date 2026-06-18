FROM node:20-bookworm-slim
WORKDIR /app

ENV NPM_CONFIG_AUDIT=false \
    NPM_CONFIG_FUND=false \
    NPM_CONFIG_UPDATE_NOTIFIER=false

COPY frontend/package*.json ./
RUN if [ -f package-lock.json ]; then npm ci --no-audit --no-fund; else npm install --no-audit --no-fund --legacy-peer-deps; fi

COPY frontend ./

ENV NEXT_PUBLIC_SUPABASE_URL=https://placeholder.supabase.co
ENV NEXT_PUBLIC_SUPABASE_ANON_KEY=placeholder-build-key
ENV NEXT_PUBLIC_API_BASE_URL=https://hwt-api.onrender.com

RUN npm run build
CMD ["npm", "run", "start"]
