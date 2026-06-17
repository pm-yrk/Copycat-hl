FROM node:22-slim
WORKDIR /app
COPY frontend/package*.json ./
RUN npm install
COPY frontend ./

# Safe build-time placeholders. Real values are read at runtime through
# /api/runtime-config from Render environment variables.
ENV NEXT_PUBLIC_SUPABASE_URL=https://placeholder.supabase.co
ENV NEXT_PUBLIC_SUPABASE_ANON_KEY=placeholder-build-key
ENV NEXT_PUBLIC_API_BASE_URL=https://hwt-api.onrender.com

RUN npm run build
CMD ["npm", "run", "start"]
