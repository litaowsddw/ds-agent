FROM node:22-alpine

WORKDIR /app

COPY apps/web/package.json /app/apps/web/package.json
COPY apps/web/package-lock.json /app/apps/web/package-lock.json
WORKDIR /app/apps/web
RUN npm ci

COPY apps/web /app/apps/web

ARG NEXT_PUBLIC_API_BASE_URL=/api
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL}
ENV NODE_ENV=production

RUN npm run build

EXPOSE 3000

CMD ["npm", "start", "--", "--hostname", "0.0.0.0", "--port", "3000"]

