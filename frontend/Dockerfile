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

# Nginx config template — BACKEND_URL is injected at container start by nginx entrypoint
COPY nginx.conf.template /etc/nginx/templates/default.conf.template

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:80/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
