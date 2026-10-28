FROM node:20-alpine
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev
COPY bot.js database.js ./
COPY privacy/node.js privacy/ui.json ./privacy/
ENV NODE_ENV=production
CMD ["node","bot.js"]
