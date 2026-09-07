FROM node:22-bookworm-slim AS web
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ARG PUBLIC_SITE_URL=http://localhost:8080
ENV PUBLIC_SITE_URL=$PUBLIC_SITE_URL
RUN npm run build

FROM python:3.12-slim-bookworm
WORKDIR /app
RUN useradd --create-home --uid 10001 tibo && mkdir /app/.data && chown tibo:tibo /app/.data
COPY --from=web /app/dist/client ./dist/client
COPY ops ./ops
COPY sample-data ./sample-data
COPY run.py ./
USER tibo
ENV HOST=0.0.0.0 PORT=8080 PYTHONUNBUFFERED=1
EXPOSE 8080
VOLUME ["/app/.data"]
CMD ["python", "run.py", "--no-build"]
