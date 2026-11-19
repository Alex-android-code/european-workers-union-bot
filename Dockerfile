FROM node:20-alpine
WORKDIR /app
COPY package.json ./
RUN npm install --omit=dev
COPY bot.js partner-vacancies.js ./
ENV NODE_ENV=production
CMD ["node","bot.js"]
