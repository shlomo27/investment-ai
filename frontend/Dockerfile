FROM node:20-alpine AS build

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .
RUN npx vite build

# Production stage
FROM nginx:alpine
RUN apk add --no-cache bash curl

# Copy built files
COPY --from=build /app/dist /usr/share/nginx/html

COPY nginx.conf.template /nginx.conf.template

RUN apk add --no-cache gettext

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:80/ || exit 1

# Substitute only ${BACKEND_URL}, leave nginx variables ($host etc.) untouched
CMD ["/bin/sh", "-c", "envsubst '${BACKEND_URL}' < /nginx.conf.template > /etc/nginx/conf.d/default.conf && nginx -g 'daemon off;'"]
