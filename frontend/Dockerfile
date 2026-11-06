FROM node:24-alpine
WORKDIR /app
COPY package.json package-lock.json ./
# Override if registry.npmjs.org is unreachable on your network, e.g. --build-arg NPM_REGISTRY=https://registry.yarnpkg.com (the lockfile's hashes still verify every package).
ARG NPM_REGISTRY=https://registry.npmjs.org
RUN npm ci --registry=$NPM_REGISTRY --fetch-retries=6 --fetch-retry-mintimeout=3000 --fetch-retry-maxtimeout=30000
COPY . .
# NEXT_PUBLIC_* values are baked into the browser bundle at build time.
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN npm run build
CMD ["npm", "run", "start"]
