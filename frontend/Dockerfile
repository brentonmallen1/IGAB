FROM node:26-alpine AS deps
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

# Production: nginx serves the static build. The config is baked in as an
# envsubst template (nginx/default.conf.template) so the published image is
# self-contained; API_UPSTREAM points the /api proxy at the backend.
FROM nginx:alpine AS production
ENV API_UPSTREAM=api:8000
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
