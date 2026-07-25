FROM node:22-alpine AS deps
WORKDIR /app
COPY package*.json ./
RUN npm ci

FROM deps AS dev
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host"]

FROM deps AS build
COPY . .
RUN npm run build

# Production: nginx serves the static build; ../nginx/nginx.conf (mounted by
# compose) handles caching headers and the /api proxy.
FROM nginx:alpine AS production
COPY --from=build /app/dist /usr/share/nginx/html
