# Linux – mTLS med Nginx, InfluxDB och Grafana (från grunden)

I denna övning skapar vi ett **nytt projekt från scratch** med **Nginx** som gateway framför **InfluxDB 2** och **Grafana**.

Nginx gör tre saker:

1) Terminerar **TLS**
2) Verifierar **klientcertifikat** (mTLS)
3) **Routar** vidare:
   - `/api/v2/...` → InfluxDB (mTLS krävs här)
   - `/...` → Grafana (frontend via Nginx; mTLS valfritt för att förenkla i webbläsare)

Vi injicerar **InfluxDB-token i Nginx** så att Python-klienten **inte** skickar `Authorization`-headern.
Allt körs i **Docker Compose** inuti en **Ubuntu 24.04-baserad Dev Container**. Alla steg görs i **bash**.

Vi använder **Conventional Commits** för att hålla en ren git-historik och sparar ofta.

---

## Resurser & dokumentation (läs mer här)

- **Git**: <https://git-scm.com/doc>
- **Conventional Commits**: <https://www.conventionalcommits.org/>
- **Docker Desktop (installation)**: <https://docs.docker.com/get-docker/>
- **Docker Compose**: <https://docs.docker.com/compose/>
- **Nginx (docs)**: <https://nginx.org/en/docs/>
  - Proxy-modul (routing): <https://nginx.org/en/docs/http/ngx_http_proxy_module.html>
  - SSL/TLS-modul: <https://nginx.org/en/docs/http/ngx_http_ssl_module.html>
- **Grafana (docs)**: <https://grafana.com/docs/grafana/latest/>
  - Konfiguration (ROOT_URL, subpath): <https://grafana.com/docs/grafana/latest/setup-grafana/configure-grafana/>
- **InfluxDB 2 (docs)**: <https://docs.influxdata.com/influxdb/v2/>
  - Write API v2: <https://docs.influxdata.com/influxdb/v2/write-data/>
- **OpenSSL**: <https://www.openssl.org/docs/>

---

## 1) Förberedelser – öppna terminal och välj arbetsmapp

### Windows

1. Öppna **Git Bash** (om du inte har det: <https://git-scm.com/downloads>)
2. Navigera till din önskade projektmapp (t.ex. `~/projects`):

    ```bash
    cd ~/projects
    ```

### macOS/Linux

1. Öppna **Terminal**
2. Navigera till din önskade projektmapp:

   ```bash
   cd ~/projects
   ```

> **Tips:** Om mappen inte finns, skapa den:
>
> ```bash
> mkdir -p ~/projects
> cd ~/projects
> ```

---

## 2) Skapa projekt och initiera Git

```bash
# Skapa projektmapp
mkdir mtls-nginx-influxdb
cd mtls-nginx-influxdb

# Initiera Git
git init

# Skapa .gitignore (kopiera in innehållet nedan till och med EOF)
cat > .gitignore << 'EOF'
# Secrets och känslig data
.env
*.pem
*.key
*.srl

# Docker
docker-compose.override.yml

# IDE
.vscode/
.idea/

# OS
.DS_Store
Thumbs.db

# Logs
*.log
EOF

# Första commit
git add .gitignore
git commit -m "chore: initialize project with gitignore"
```

> **Conventional Commits snabbguide:**
>
> - `feat:` – ny funktionalitet
> - `fix:` – buggfix
> - `docs:` – dokumentation
> - `chore:` – underhåll (dependencies, config)
> - `refactor:` – kodförbättring utan funktionsändring
> - `test:` – tester

---

## 3) Skapa projektstruktur

```bash
# Skapa mappar
mkdir -p certs nginx grafana/datasources client

# Verifiera struktur
tree -L 1
# Eller om tree inte finns:
ls -la
```

Expected output:

```text
mtls-nginx-influxdb/
├── .git/
├── .gitignore
├── certs/
├── client/
├── grafana/
└── nginx/
```

Commit:

```bash
git add .
git commit -m "chore: create project directory structure"
```

---

## 4) Skapa .env-fil (miljövariabler)

```bash
cat > .env << 'EOF'
# InfluxDB bootstrap
DOCKER_INFLUXDB_INIT_MODE=setup
DOCKER_INFLUXDB_INIT_USERNAME=admin
DOCKER_INFLUXDB_INIT_PASSWORD=adminpassword123
DOCKER_INFLUXDB_INIT_ORG=tutorial
DOCKER_INFLUXDB_INIT_BUCKET=metrics
DOCKER_INFLUXDB_INIT_ADMIN_TOKEN=my-super-secret-auth-token

# Nginx host-port (vad du öppnar på din dator)
NGINX_HTTPS_PORT=8443

# Nginx injicerar detta (Auth till InfluxDB)
INFLUX_TOKEN=${DOCKER_INFLUXDB_INIT_ADMIN_TOKEN}
EOF
```

> **VIKTIGT:** `.env` finns i `.gitignore` – den sparas **inte** i git!

Skapa exempel-fil för dokumentation:

```bash
cat > .env.example << 'EOF'
# InfluxDB bootstrap
DOCKER_INFLUXDB_INIT_MODE=setup
DOCKER_INFLUXDB_INIT_USERNAME=admin
DOCKER_INFLUXDB_INIT_PASSWORD=CHANGE_ME
DOCKER_INFLUXDB_INIT_ORG=tutorial
DOCKER_INFLUXDB_INIT_BUCKET=metrics
DOCKER_INFLUXDB_INIT_ADMIN_TOKEN=CHANGE_ME

# Nginx host-port
NGINX_HTTPS_PORT=8443

# Nginx injicerar detta
INFLUX_TOKEN=${DOCKER_INFLUXDB_INIT_ADMIN_TOKEN}
EOF

git add .env.example
git commit -m "chore: add environment variables template"
```

---

## 5) Generera certifikat för mTLS (manuellt)

Vi behöver tre certifikat för vår PKI (Public Key Infrastructure):

1. **CA (Certificate Authority)** – självsignerat rotcertifikat
2. **Server-certifikat** – för Nginx (med SAN för localhost och nginx-mtls)
3. **Klient-certifikat** – för metrics-client

> **Viktigt:** Den privata nyckeln lämnar aldrig enheten den skapas på. Endast CSR (Certificate Signing Request) skickas till CA för signering.

### Steg 1: Skapa självsignerad CA

```bash
cd certs

# Generera CA:s privata nyckel (2048-bit RSA)
openssl genrsa -out ca-key.pem 2048
chmod 600 ca-key.pem

# Skapa självsignerat CA-certifikat (giltigt 365 dagar)
openssl req -x509 -new -nodes -key ca-key.pem -sha256 -days 365 -out ca-cert.pem
```

**När du blir tillfrågad, fyll i:**

- Country Name: `SE`
- State: `Stockholm`
- Locality: `Nacka`
- Organization Name: `Nackademin`
- Organizational Unit Name: `IoT` (valfritt, kan lämnas tomt)
- Common Name: `Nackademin-CA`
- Email Address: (valfritt, kan lämnas tomt)

> Certifikaten sparas **inte** i git (finns i `.gitignore`)

---

### Steg 2: Skapa server-certifikat för Nginx (med SAN)

Moderna webbläsare och klienter kräver **SAN (Subject Alternative Name)** – de ignorerar Common Name (CN).

```bash
# Generera server privat nyckel
openssl genrsa -out server-key.pem 2048
chmod 600 server-key.pem

# Skapa config-fil för SAN (Subject Alternative Name), kopiera in nedan till och med EOF
cat > server-san.cnf << 'EOF'
[req]
default_bits = 2048
prompt = no
default_md = sha256
distinguished_name = dn
req_extensions = v3_req

[dn]
C=SE
ST=Stockholm
L=Nacka
O=Nackademin
CN=nginx-mtls

[v3_req]
subjectAltName = @alt_names

[alt_names]
DNS.1 = nginx-mtls
DNS.2 = localhost
IP.1 = 127.0.0.1
EOF

# Skapa CSR (Certificate Signing Request)
openssl req -new -key server-key.pem -out server-csr.pem -config server-san.cnf

# Signera CSR med CA (inkludera SAN-extensions)
openssl x509 -req -days 365 \
  -in server-csr.pem \
  -CA ca-cert.pem \
  -CAkey ca-key.pem \
  -CAcreateserial \
  -out server-cert.pem \
  -extensions v3_req \
  -extfile server-san.cnf

# Städa upp temporära filer
rm server-csr.pem server-san.cnf

```

**Verifiera SAN:**

```bash
openssl x509 -in certs/server-cert.pem -noout -text | grep -A1 "Subject Alternative Name"
```

Expected output:

```text
X509v3 Subject Alternative Name:
    DNS:nginx-mtls, DNS:localhost, IP Address:127.0.0.1
```

---

### Steg 3: Skapa klient-certifikat för metrics-client

```bash

# Generera klient privat nyckel
openssl genrsa -out client-key.pem 2048
chmod 600 client-key.pem

# Skapa CSR för klienten
openssl req -new -key client-key.pem -out client-csr.pem \
  -subj "/C=SE/ST=Stockholm/L=Solna/O=Tutorial/CN=metrics-client"

# Signera CSR med CA
openssl x509 -req -days 365 \
  -in client-csr.pem \
  -CA ca-cert.pem \
  -CAkey ca-key.pem \
  -CAcreateserial \
  -out client-cert.pem

# Städa upp
rm client-csr.pem 
```

---

### Steg 4: Verifiera certifikatkedjan

```bash
# Verifiera server-certifikatet
openssl verify -CAfile ca-cert.pem server-cert.pem

# Verifiera klient-certifikatet
openssl verify -CAfile ca-cert.pem client-cert.pem
```

Expected output för båda:

```text
server-cert.pem: OK
client-cert.pem: OK
```

---

### Steg 5: Inspektera certifikat (valfritt)

> ``less`` is ``more`` och är bra för att scrolla i långa outputs. ``cat`` fungerar också men scrollar inte. Avslut med `q` i less.

```bash
# Visa server-certifikat i detalj
openssl x509 -in server-cert.pem -noout -text | less

# Visa klient-certifikat
openssl x509 -in client-cert.pem -noout -text | less

# Visa CA-certifikat
openssl x509 -in ca-cert.pem -noout -text | less
```

---

### Sammanfattning av certifikat

Efter detta steg har du:

```text
certs/
├── ca-cert.pem         (CA:s publika certifikat - distribueras till klienter)
├── ca-key.pem          (CA:s privata nyckel - håll hemlig!)
├── ca.srl              (serial number file - genereras automatiskt)
├── server-cert.pem     (Nginx server certifikat)
├── server-key.pem      (Nginx privat nyckel)
├── client-cert.pem     (Metrics-client certifikat)
└── client-key.pem      (Metrics-client privat nyckel)
```

> **Säkerhet:**
>
> - Privata nycklar (`*-key.pem`) får **aldrig** delas eller checkas in i git
> - I produktion: använd Hardware Security Modules (HSM) för CA-nyckeln
> - Rotera certifikat regelbundet (t.ex. var 90:e dag)

---

## 6) Skapa Nginx-konfiguration

```bash
# Gå till projektrotmappen med cd.. om du är i certs/
cd ..

cat > nginx/nginx.conf << 'EOF'
env INFLUX_TOKEN;

events { worker_connections 1024; }

http {
  upstream influxdb { server influxdb:8086; }
  upstream grafana  { server grafana:3000; }

  map $http_upgrade $connection_upgrade {
    default upgrade;
    '' close;
  }

  server {
    listen 443 ssl;
    server_name localhost nginx-mtls;

    ssl_certificate      /etc/nginx/certs/server-cert.pem;
    ssl_certificate_key  /etc/nginx/certs/server-key.pem;

    ssl_client_certificate /etc/nginx/certs/ca-cert.pem;
    ssl_verify_client optional;
    ssl_verify_depth 2;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    proxy_http_version 1.1;
    proxy_request_buffering off;
    proxy_buffering off;
    proxy_read_timeout 300s;

    location = /health {
      access_log off;
      add_header Content-Type text/plain;
      return 200 "OK\n";
    }

    location /api/v2/ {
      if ($ssl_client_verify != SUCCESS) { return 495; }

      proxy_pass http://influxdb;
      proxy_set_header Authorization "Token $INFLUX_TOKEN";
      proxy_set_header Host $host;
      proxy_set_header X-Real-IP $remote_addr;
      proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
      proxy_set_header X-Forwarded-Proto $scheme;
    }

    location / {
      proxy_pass http://grafana;
      proxy_set_header Host $host;
    }


    # Proxy Grafana Live WebSocket connections.
    location /api/live/ {
       proxy_http_version 1.1;
       proxy_set_header Upgrade $http_upgrade;
       proxy_set_header Connection $connection_upgrade;
       proxy_set_header Host $host;
       proxy_pass http://grafana;
    }
  }
}
EOF

git add nginx/nginx.conf
git commit -m "feat: add nginx configuration with mTLS and routing"
```

---

## 7) Skapa Nginx Dockerfile

```bash
cat > nginx/Dockerfile << 'EOF'
FROM nginx:alpine

# Installera gettext för envsubst
RUN apk add --no-cache gettext

# Kopiera config template
COPY nginx.conf /etc/nginx/nginx.conf.template

# Entrypoint som injicerar INFLUX_TOKEN
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["nginx", "-g", "daemon off;"]
EOF

# Skapa entrypoint script för dockerfilen som injicerar INFLUX_TOKEN
cat > nginx/docker-entrypoint.sh << 'EOF'
#!/bin/sh
set -e

# Injicera INFLUX_TOKEN i nginx config
envsubst '$INFLUX_TOKEN' < /etc/nginx/nginx.conf.template > /etc/nginx/nginx.conf

exec "$@"
EOF

# Ge scriptet körbar rättighet
chmod +x nginx/docker-entrypoint.sh

git add nginx/Dockerfile nginx/docker-entrypoint.sh
git commit -m "feat: add nginx dockerfile with env variable injection"
```

---

## 8) Skapa Grafana datasource provisioning

```bash
cat > grafana/datasources/influxdb.yml << 'EOF'
apiVersion: 1

datasources:
  - name: InfluxDB
    type: influxdb
    access: proxy
    url: http://influxdb:8086
    jsonData:
      version: Flux
      organization: tutorial
      defaultBucket: metrics
      tlsSkipVerify: true
    secureJsonData:
      token: my-super-secret-auth-token
EOF

git add grafana/datasources/
git commit -m "feat: add grafana datasource provisioning for influxdb"
```

---

## 9) Skapa Python metrics client

```bash
# Skapa Dockerfile för klienten
cat > client/Dockerfile << 'EOF'
FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir influxdb-client requests

COPY app.py .

CMD ["python", "app.py"]
EOF

# Skapa Python app som skickar metrics till InfluxDB via Nginx med mTLS
cat > client/app.py << 'EOF'
import os
import time
import random
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

# Config från env
NGINX_HOST = os.getenv("NGINX_HOST", "nginx-mtls")
NGINX_PORT = os.getenv("NGINX_PORT", "443")
INFLUX_ORG = os.getenv("INFLUX_ORG", "tutorial")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET", "metrics")

# mTLS certs
CA_CERT = "/app/certs/ca-cert.pem"
CLIENT_CERT = "/app/certs/client-cert.pem"
CLIENT_KEY = "/app/certs/client-key.pem"

# InfluxDB client (token injiceras av Nginx, skicka tom sträng)
url = f"https://{NGINX_HOST}:{NGINX_PORT}"
client = InfluxDBClient(
    url=url,
    org=INFLUX_ORG,
    token="",  # Nginx injicerar token
    ssl_ca_cert=CA_CERT,
    cert_file=CLIENT_CERT,
    cert_key_file=CLIENT_KEY,
    verify_ssl=True
)

write_api = client.write_api(write_options=SYNCHRONOUS)

print(f"Starting metrics client, writing to {url}")

while True:
    try:
        # Simulera system metrics
        cpu = random.uniform(10, 90)
        memory = random.uniform(30, 80)

        point = Point("system_metrics") \
            .tag("host", "metrics-client") \
            .field("cpu_usage", cpu) \
            .field("memory_usage", memory)

        write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)
        print(f"✓ Wrote metrics: CPU={cpu:.1f}%, Memory={memory:.1f}%")

    except Exception as e:
        print(f"✗ Error writing metrics: {e}")

    time.sleep(10)
EOF

git add client/
git commit -m "feat: add python metrics client with mTLS support"
```

---

## 10) Skapa Docker Compose

```bash
cat > docker-compose.yml << 'EOF'
networks:
  metrics-net:
    name: metrics-net
    driver: bridge

services:
  nginx:
    build: ./nginx
    container_name: nginx-mtls
    ports:
      - "${NGINX_HTTPS_PORT}:443"
    environment:
      - INFLUX_TOKEN=${INFLUX_TOKEN}
    volumes:
      - ./certs:/etc/nginx/certs:ro
    depends_on:
      - influxdb
      - grafana
    networks:
      metrics-net:
        aliases:
          - nginx-mtls

  influxdb:
    image: influxdb:2.7
    container_name: influxdb
    environment:
      - DOCKER_INFLUXDB_INIT_MODE=${DOCKER_INFLUXDB_INIT_MODE}
      - DOCKER_INFLUXDB_INIT_USERNAME=${DOCKER_INFLUXDB_INIT_USERNAME}
      - DOCKER_INFLUXDB_INIT_PASSWORD=${DOCKER_INFLUXDB_INIT_PASSWORD}
      - DOCKER_INFLUXDB_INIT_ORG=${DOCKER_INFLUXDB_INIT_ORG}
      - DOCKER_INFLUXDB_INIT_BUCKET=${DOCKER_INFLUXDB_INIT_BUCKET}
      - DOCKER_INFLUXDB_INIT_ADMIN_TOKEN=${DOCKER_INFLUXDB_INIT_ADMIN_TOKEN}
    volumes:
      - influxdb-data:/var/lib/influxdb2
    networks:
      - metrics-net

  grafana:
    image: grafana/grafana:latest
    container_name: grafana
    environment:
      - GF_SECURITY_ADMIN_USER=admin
      - GF_SECURITY_ADMIN_PASSWORD=admin
      - GF_SERVER_ROOT_URL=https://localhost:${NGINX_HTTPS_PORT}
    volumes:
      - grafana-data:/var/lib/grafana
      - ./grafana/datasources:/etc/grafana/provisioning/datasources
    depends_on:
      - influxdb
    networks:
      - metrics-net

  metrics-client:
    build: ./client
    container_name: metrics-client
    volumes:
      - ./certs:/app/certs:ro
    environment:
      - NGINX_HOST=nginx-mtls
      - NGINX_PORT=443
      - INFLUX_ORG=${DOCKER_INFLUXDB_INIT_ORG}
      - INFLUX_BUCKET=${DOCKER_INFLUXDB_INIT_BUCKET}
    depends_on:
      - nginx
      - influxdb
    networks:
      - metrics-net

volumes:
  influxdb-data:
  grafana-data:
EOF

git add docker-compose.yml
git commit -m "feat: add docker-compose configuration with complete stack"
```

---

## 11) Starta och verifiera

### Starta stacken

```bash
docker compose up -d --build
docker compose ps
```

### Verifiera hälsa

```bash
# Läs NGINX_HTTPS_PORT från .env
source .env

# Testa health endpoint
curl --cacert certs/ca-cert.pem \
     --cert certs/client-cert.pem \
     --key certs/client-key.pem \
     https://localhost:${NGINX_HTTPS_PORT}/health
```

Expected: `OK`

### Skriv testdata

```bash
curl --cacert certs/ca-cert.pem \
     --cert certs/client-cert.pem \
     --key certs/client-key.pem \
     -H 'Content-Type: text/plain' \
     "https://localhost:${NGINX_HTTPS_PORT}/api/v2/write?org=tutorial&bucket=metrics&precision=ns" \
     --data-raw "test_metric,host=manual value=42i"
```

### Öppna Grafana

1. Gå till: `https://localhost:8443/grafana`
2. Logga in: `admin` / `admin`
3. Explore → InfluxDB → Query:

```flux
from(bucket: "metrics")
  |> range(start: -10m)
  |> filter(fn: (r) => r._measurement == "system_metrics")
```

Du ska se metrics från `metrics-client`.

---

## 12) Vanliga kommandon

### Loggar

```bash
docker compose logs -f nginx
docker compose logs -f metrics-client
docker compose logs -f influxdb
```

### Starta om en tjänst

```bash
docker compose restart nginx
```

### Rebuilda efter ändringar

```bash
docker compose up -d --build nginx
```

### Inspektera nätverk

```bash
docker network inspect metrics-net
```

### Kör kommando i container

```bash
docker compose exec metrics-client sh
docker compose exec nginx sh
```

---

## 13) Felsökning

### Grafana ser trasig ut (CSS/JS 404)

Kontrollera:

- `nginx.conf`: `location /grafana/` har `proxy_pass http://grafana/;`
- Grafana env:
  - `GF_SERVER_ROOT_URL=https://localhost:8443/grafana/`
  - `GF_SERVER_SERVE_FROM_SUB_PATH=true`

### Nginx ger 495 (cert required)

Du saknar klientcertifikat:

```bash
# Testa med OpenSSL
openssl s_client -connect localhost:8443 \
  -CAfile certs/ca-cert.pem \
  -cert certs/client-cert.pem \
  -key certs/client-key.pem \
  -servername nginx-mtls </dev/null
```

### Port konflikt (8443 används)

```bash
# Se vad som använder porten
ss -tlnp | grep 8443

# Ändra port i .env
echo "NGINX_HTTPS_PORT=9443" >> .env
docker compose down
docker compose up -d
```

---

## 14) Städa upp

```bash
# Stoppa och ta bort containers + volymer
docker compose down -v

# Ta bort certifikat (om du vill återskapa)
rm -f certs/*.pem certs/*.srl
```

---
