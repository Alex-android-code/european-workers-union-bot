FROM node:20-alpine
WORKDIR /app
RUN apk add --no-cache util-linux
COPY package.json package-lock.json ./
RUN npm ci --omit=dev --ignore-scripts
COPY bot.js bot-core.mjs sync.mjs delivery.mjs intake-lock.mjs ./
ENV NODE_ENV=production
CMD ["node","bot.js"]
