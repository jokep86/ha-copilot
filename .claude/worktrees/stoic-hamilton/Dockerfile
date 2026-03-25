ARG BUILD_FROM
FROM $BUILD_FROM

ENV LANG=C.UTF-8
WORKDIR /app

# System deps for Python packages (aiohttp, cryptography, kaleido)
RUN apk add --no-cache \
    gcc \
    musl-dev \
    libffi-dev \
    openssl-dev \
    chromium \
    chromium-chromedriver

COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY app/ /app/app/
COPY prompts/ /app/prompts/
COPY migrations/ /app/migrations/
COPY run.sh /run.sh

RUN chmod +x /run.sh

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD wget -qO- http://localhost:8099/health || exit 1

CMD ["/run.sh"]
