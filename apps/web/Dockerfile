FROM node:22-alpine

WORKDIR /app

COPY apps/web/package.json /app/apps/web/package.json
WORKDIR /app/apps/web
RUN npm install

COPY apps/web /app/apps/web

CMD ["npm", "run", "dev", "--", "--hostname", "0.0.0.0", "--port", "3000"]

