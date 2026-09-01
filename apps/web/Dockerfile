# The frontend is static once built, so the image that builds it is not the
# image that serves it. Caddy serves the output; this stage exists only to
# produce dist/ reproducibly rather than depending on whatever Node happens to
# be on the machine doing the deploy.
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
COPY apps/web/package.json ./apps/web/
RUN npm ci || npm install
COPY . .
RUN npm --workspace apps/web run build

FROM alpine:3.20
COPY --from=build /app/apps/web/dist /dist
