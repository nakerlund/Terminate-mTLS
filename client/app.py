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
