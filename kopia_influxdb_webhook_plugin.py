import os
import re
import logging
from flask import Flask, request, jsonify
from datetime import datetime
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

app = Flask(__name__)

# Logging configuration
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(message)s"
)
logger = logging.getLogger("kopia_influxdb_webhook_plugin")
app.logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

# InfluxDB configuration from environment variables
INFLUX_URL = os.getenv("INFLUX_URL")
INFLUX_TOKEN = os.getenv("INFLUX_TOKEN")
INFLUX_ORG = os.getenv("INFLUX_ORG")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET")

if not all([INFLUX_URL, INFLUX_TOKEN, INFLUX_ORG, INFLUX_BUCKET]):
    raise RuntimeError("Missing one or more InfluxDB environment variables: INFLUX_URL, INFLUX_TOKEN, INFLUX_ORG, INFLUX_BUCKET")

# Initialize InfluxDB client
client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
write_api = client.write_api(write_options=SYNCHRONOUS)

# Precompile regex patterns
VERSION_RE = re.compile(r"Kopia Version:\s*\*\*(?P<version>[0-9\.]+)\*\*")
BUILD_RE = re.compile(r"Build Info:\s*\*\*(?P<build>[0-9a-f]+)\*\*")
REPO_RE = re.compile(r"Github Repo:\s*\*\*(?P<repo>[^*]+)\*\*")
PATH_RE = re.compile(r"Path:\s*(?P<path>.+)")
STATUS_RE = re.compile(r"Status:\s*(?P<status>\w+)")
START_RE = re.compile(r"Start:\s*(?P<start>.+)")
DURATION_RE = re.compile(r"Duration:\s*(?P<duration>[\d\.]+(?:ms|s))")
SIZE_RE = re.compile(r"Size:\s*(?P<size>[\d\.]+\s*[KMG]?B)(?:\s*\(\+(?P<delta>[\d\.]+\s*[KMG]?B)\))?")
FILES_RE = re.compile(r"Files:\s*(?P<files>\d+)(?:\s*\(\+(?P<files_delta>\d+)\))?")
DIRS_RE = re.compile(r"Directories:\s*(?P<dirs>\d+)")
ERROR_RE = re.compile(r"Error:\s*(?P<error>.+)")
DATE_FORMAT = "%a, %d %b %Y %H:%M:%S %z"

# Helpers

def parse_duration(val):
    if val.endswith('ms'):
        return float(val[:-2]) / 1000.0
    if val.endswith('s'):
        return float(val[:-1])
    return float(val)


def parse_size(val):
    """Convert sizes like '2.3 MB' or '104.4 MB' to bytes"""
    units = {'B': 1, 'KB': 1<<10, 'MB': 1<<20, 'GB': 1<<30}
    num, unit = val.strip().split()
    unit = unit.upper()
    return float(num) * units.get(unit, 1)

@app.route('/webhook', methods=['POST'])
def webhook():
    headers = dict(request.headers)
    raw_body = request.data.decode('utf-8', errors='replace')

    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(f"Headers: {headers}")
        logger.debug(f"Raw body: {raw_body}")

    subject = headers.get('Subject', '')
    host = headers.get('Host', 'unknown')
    kopia_instance = headers.get('Instance', 'unknown')
    kopia_client_ip = request.remote_addr

    # Determine event type
    if subject.lower().startswith('test notification'):
        # Test notification
        version = VERSION_RE.search(raw_body)
        build = BUILD_RE.search(raw_body)
        repo = REPO_RE.search(raw_body)

        p = Point("kopia_test_notification")
        p.tag("host", host)
        p.tag("instance_name", kopia_instance)
        p.tag("client_ip", kopia_client_ip)
        if version:
            p.tag("version", version.group('version'))
        if build:
            p.tag("build", build.group('build'))
        if repo:
            p.tag("repo", repo.group('repo'))
        p.field("count", 1)

    else:
        # Snapshot event
        path = PATH_RE.search(raw_body)
        status = STATUS_RE.search(raw_body)
        start = START_RE.search(raw_body)
        duration = DURATION_RE.search(raw_body)
        size = SIZE_RE.search(raw_body)
        files = FILES_RE.search(raw_body)
        dirs = DIRS_RE.search(raw_body)
        error = ERROR_RE.search(raw_body)

        # Parse values
        path_val = path.group('path').strip() if path else 'unknown'
        status_val = status.group('status') if status else 'unknown'
        start_val = None
        if start:
            try:
                start_val = datetime.strptime(start.group('start').strip(), DATE_FORMAT)
            except Exception:
                start_val = None

        duration_val = parse_duration(duration.group('duration')) if duration else 0.0
        size_val = parse_size(size.group('size')) if size else 0.0
        delta_val = parse_size(size.group('delta')) if (size and size.group('delta')) else 0.0
        files_val = int(files.group('files')) if files else 0
        files_delta = int(files.group('files_delta')) if (files and files.group('files_delta')) else 0
        dirs_val = int(dirs.group('dirs')) if dirs else 0
        error_msg = error.group('error').strip() if error else ''

        p = Point("kopia_snapshot")
        p.tag("host", host)
        p.tag("instance_name", kopia_instance)
        p.tag("client_ip", kopia_client_ip)
        p.tag("path", path_val)
        p.tag("status", status_val)
        if error_msg:
            p.field("error", error_msg)
        p.field("duration_seconds", duration_val)
        p.field("size_bytes", size_val)
        p.field("size_delta_bytes", delta_val)
        p.field("files", files_val)
        p.field("files_delta", files_delta)
        p.field("directories", dirs_val)

        if start_val:
            p.time(start_val)

    # Write to InfluxDB
    try:
        write_api.write(bucket=INFLUX_BUCKET, record=p)
        logger.info("Wrote point to InfluxDB")
    except Exception as e:
        logger.error(f"InfluxDB write failed: {e}")
        return jsonify({'error': 'influx write failed'}), 500

    return jsonify({'result': 'ok'}), 200

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    logger.info(f"Starting server on port {port}")
    app.run(host='0.0.0.0', port=port)