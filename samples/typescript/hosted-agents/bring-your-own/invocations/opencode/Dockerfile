FROM node:26.4.0-bookworm-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY tsconfig.json ./
COPY src ./src
RUN npm run build && npm prune --omit=dev

FROM node:26.4.0-bookworm-slim AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && apt-get clean
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=8088
ENV XDG_DATA_HOME=/tmp/opencode/data \
    XDG_CACHE_HOME=/tmp/opencode/cache \
    XDG_CONFIG_HOME=/tmp/opencode/config \
    XDG_STATE_HOME=/tmp/opencode/state
COPY --from=build --chown=node:node /app/package.json /app/package-lock.json ./
COPY --from=build --chown=node:node /app/node_modules ./node_modules
COPY --from=build --chown=node:node /app/dist ./dist
USER node
EXPOSE 8088
CMD ["node", "dist/server.js"]
