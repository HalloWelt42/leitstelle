# Leitstelle auf dem Pi. Ein Abbild je Dienst über Bauziele:
#   leitstelle  Kern mit Fassade, Verwaltung, Kanal und Oberfläche (Port 8530)
#   entwuerfe   die Entwürfe als Leitfaden (Port 8535)
# Der Bau scheitert, wenn ein Test rot ist oder die Oberfläche Typfehler hat; ausgeliefert wird nur Geprüftes.

# ── Kern: Abhängigkeiten und alle Tests auf der Zielarchitektur ───────────
FROM python:3.13-slim AS kern
WORKDIR /app
COPY version.json ./
COPY backend/ backend/
COPY tools/schein_laeufer.py tools/messen_fassade.py tools/
# Der Maschinenraum (eigenes Repo) dient als echter Knoten-Agent in den Ende-zu-Ende-Tests
ARG MASCHINENRAUM=https://github.com/HalloWelt42/maschinenraum/archive/refs/heads/main.tar.gz
RUN pip install --no-cache-dir -e "backend[test]" "$MASCHINENRAUM" \
 && cd /app/backend && python -m pytest -q -p no:cacheprovider \
 && echo "geprüft" > /app/kern-geprueft

# ── Oberfläche: prüfen und bauen ─────────────────────────────────────────
FROM node:22-alpine AS oberflaeche
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npx svelte-check --tsconfig ./tsconfig.json --fail-on-warnings && npm run build

# ── Laufzeit des Kerns ───────────────────────────────────────────────────
FROM python:3.13-slim AS leitstelle
WORKDIR /app
COPY version.json ./
COPY backend/ backend/
RUN pip install --no-cache-dir -e backend && rm -rf backend/tests
COPY --from=kern /app/kern-geprueft /app/kern-geprueft
COPY --from=oberflaeche /app/frontend/dist /app/oberflaeche
ENV LEITSTELLE_DATEN=/daten LEITSTELLE_OBERFLAECHE=/app/oberflaeche LEITSTELLE_PORT=8530 PYTHONUNBUFFERED=1
EXPOSE 8530
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8530/gesundheit', timeout=4).status == 200 else 1)"
CMD ["python", "-m", "leitstelle"]

# ── Entwürfe ─────────────────────────────────────────────────────────────
FROM nginx:1.27-alpine AS entwuerfe
COPY deploy/nginx-entwuerfe.conf /etc/nginx/conf.d/default.conf
COPY --from=kern /app/kern-geprueft /usr/share/nginx/html/kern-geprueft
COPY --from=oberflaeche /app/frontend/node_modules/@fontsource /usr/share/nginx/html/frontend/node_modules/@fontsource
COPY --from=oberflaeche /app/frontend/node_modules/@fortawesome /usr/share/nginx/html/frontend/node_modules/@fortawesome
COPY mockups/ /usr/share/nginx/html/mockups/
COPY version.json /usr/share/nginx/html/version.json
