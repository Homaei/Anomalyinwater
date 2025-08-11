#!/bin/bash

# WWTP Anomaly Detection System - Monitoring Setup Script
# This script sets up comprehensive monitoring and alerting

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MONITORING_DIR="/var/lib/wwtp-monitoring"
ALERT_EMAIL="${ALERT_EMAIL:-admin@example.com}"
SLACK_WEBHOOK="${SLACK_WEBHOOK:-}"

# Functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

create_monitoring_directories() {
    log_info "Creating monitoring directories..."
    
    mkdir -p "$MONITORING_DIR"/{prometheus,grafana,alertmanager,exporters}
    mkdir -p /var/log/wwtp-monitoring
    
    # Set permissions
    chown -R 65534:65534 "$MONITORING_DIR/prometheus"  # nobody user
    chown -R 472:472 "$MONITORING_DIR/grafana"         # grafana user
    chown -R 65534:65534 "$MONITORING_DIR/alertmanager" # nobody user
    
    log_success "Monitoring directories created"
}

setup_prometheus_config() {
    log_info "Setting up Prometheus configuration..."
    
    # Copy base configuration
    cp "$PROJECT_DIR/infrastructure/prometheus/"* "$MONITORING_DIR/prometheus/"
    
    # Create additional scrape configs
    cat >> "$MONITORING_DIR/prometheus/prometheus.yml" << EOF

  # Additional monitoring targets
  - job_name: 'system-metrics'
    static_configs:
      - targets: ['localhost:9100']  # node-exporter
    scrape_interval: 15s

  - job_name: 'docker-metrics'
    static_configs:
      - targets: ['localhost:8080']  # cadvisor
    scrape_interval: 15s

  - job_name: 'nginx-metrics'
    static_configs:
      - targets: ['nginx-exporter:9113']
    scrape_interval: 15s

  # Custom application metrics
  - job_name: 'custom-metrics'
    static_configs:
      - targets: ['custom-exporter:9999']
    scrape_interval: 30s
    metrics_path: /metrics
    honor_labels: true

  # File-based service discovery
  - job_name: 'file-discovery'
    file_sd_configs:
      - files:
          - '/etc/prometheus/targets/*.yml'
        refresh_interval: 30s
EOF
    
    # Create service discovery directory
    mkdir -p "$MONITORING_DIR/prometheus/targets"
    
    # Create dynamic targets file
    cat > "$MONITORING_DIR/prometheus/targets/dynamic.yml" << EOF
- targets:
    - 'localhost:9090'
  labels:
    job: 'prometheus'
    environment: '${ENVIRONMENT:-production}'
EOF
    
    log_success "Prometheus configuration updated"
}

setup_alertmanager() {
    log_info "Setting up Alertmanager..."
    
    # Create Alertmanager configuration
    cat > "$MONITORING_DIR/alertmanager/alertmanager.yml" << EOF
global:
  smtp_smarthost: '${SMTP_HOST:-localhost:587}'
  smtp_from: '${SMTP_FROM:-alerts@wwtp.local}'
  smtp_auth_username: '${SMTP_USER:-}'
  smtp_auth_password: '${SMTP_PASS:-}'

route:
  group_by: ['alertname', 'cluster', 'service']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 1h
  receiver: 'web.hook'
  routes:
  - match:
      severity: critical
    receiver: 'critical-alerts'
  - match:
      severity: warning
    receiver: 'warning-alerts'
  - match:
      service: database
    receiver: 'database-alerts'

receivers:
- name: 'web.hook'
  webhook_configs:
  - url: 'http://localhost:5001/webhook'
    send_resolved: true

- name: 'critical-alerts'
  email_configs:
  - to: '${ALERT_EMAIL}'
    subject: 'CRITICAL ALERT: {{ .GroupLabels.alertname }}'
    body: |
      Alert: {{ .GroupLabels.alertname }}
      Severity: {{ .CommonLabels.severity }}
      Instance: {{ .CommonLabels.instance }}
      Summary: {{ range .Alerts }}{{ .Annotations.summary }}{{ end }}
      Description: {{ range .Alerts }}{{ .Annotations.description }}{{ end }}
      
      Time: {{ .CommonLabels.timestamp }}
      
      View in Grafana: http://localhost:3001
      
  slack_configs:
  - api_url: '${SLACK_WEBHOOK}'
    channel: '#alerts'
    title: 'CRITICAL: {{ .GroupLabels.alertname }}'
    text: |
      {{ range .Alerts }}
      *Alert:* {{ .Annotations.summary }}
      *Severity:* {{ .Labels.severity }}
      *Instance:* {{ .Labels.instance }}
      *Description:* {{ .Annotations.description }}
      {{ end }}

- name: 'warning-alerts'
  email_configs:
  - to: '${ALERT_EMAIL}'
    subject: 'WARNING: {{ .GroupLabels.alertname }}'
    body: |
      Alert: {{ .GroupLabels.alertname }}
      Severity: {{ .CommonLabels.severity }}
      Instance: {{ .CommonLabels.instance }}
      Summary: {{ range .Alerts }}{{ .Annotations.summary }}{{ end }}

- name: 'database-alerts'
  email_configs:
  - to: '${ALERT_EMAIL}'
    subject: 'DATABASE ALERT: {{ .GroupLabels.alertname }}'
    body: |
      Database Alert: {{ .GroupLabels.alertname }}
      Instance: {{ .CommonLabels.instance }}
      Details: {{ range .Alerts }}{{ .Annotations.description }}{{ end }}

inhibit_rules:
- source_match:
    severity: 'critical'
  target_match:
    severity: 'warning'
  equal: ['alertname', 'cluster', 'service']
EOF
    
    log_success "Alertmanager configured"
}

setup_grafana_dashboards() {
    log_info "Setting up Grafana dashboards..."
    
    # Copy existing dashboard configurations
    cp -r "$PROJECT_DIR/infrastructure/grafana/"* "$MONITORING_DIR/grafana/"
    
    # Create comprehensive system dashboard
    cat > "$MONITORING_DIR/grafana/dashboards/system-overview.json" << 'EOF'
{
  "dashboard": {
    "id": null,
    "title": "WWTP System Overview",
    "tags": ["wwtp", "system", "overview"],
    "timezone": "browser",
    "panels": [
      {
        "id": 1,
        "title": "System Health Score",
        "type": "stat",
        "gridPos": {"h": 8, "w": 6, "x": 0, "y": 0},
        "targets": [
          {
            "expr": "wwtp:app_health_score",
            "refId": "A"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "min": 0,
            "max": 1,
            "thresholds": {
              "steps": [
                {"color": "red", "value": 0},
                {"color": "yellow", "value": 0.7},
                {"color": "green", "value": 0.9}
              ]
            }
          }
        }
      },
      {
        "id": 2,
        "title": "CPU Usage",
        "type": "graph",
        "gridPos": {"h": 8, "w": 6, "x": 6, "y": 0},
        "targets": [
          {
            "expr": "wwtp:cpu_utilization",
            "refId": "A"
          }
        ]
      },
      {
        "id": 3,
        "title": "Memory Usage",
        "type": "graph",
        "gridPos": {"h": 8, "w": 6, "x": 12, "y": 0},
        "targets": [
          {
            "expr": "wwtp:memory_utilization * 100",
            "refId": "A"
          }
        ]
      },
      {
        "id": 4,
        "title": "Disk Usage",
        "type": "graph",
        "gridPos": {"h": 8, "w": 6, "x": 18, "y": 0},
        "targets": [
          {
            "expr": "wwtp:disk_utilization * 100",
            "refId": "A"
          }
        ]
      },
      {
        "id": 5,
        "title": "Request Rate",
        "type": "graph",
        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 8},
        "targets": [
          {
            "expr": "sum(rate(http_requests_total[5m])) by (job)",
            "refId": "A"
          }
        ]
      },
      {
        "id": 6,
        "title": "Error Rate",
        "type": "graph",
        "gridPos": {"h": 8, "w": 12, "x": 12, "y": 8},
        "targets": [
          {
            "expr": "wwtp:http_error_rate * 100",
            "refId": "A"
          }
        ]
      },
      {
        "id": 7,
        "title": "ML Processing Rate",
        "type": "graph",
        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 16},
        "targets": [
          {
            "expr": "wwtp:ml_processing_rate",
            "refId": "A"
          }
        ]
      },
      {
        "id": 8,
        "title": "Database Connections",
        "type": "graph",
        "gridPos": {"h": 8, "w": 12, "x": 12, "y": 16},
        "targets": [
          {
            "expr": "wwtp:db_connection_utilization * 100",
            "refId": "A"
          }
        ]
      }
    ],
    "time": {
      "from": "now-1h",
      "to": "now"
    },
    "refresh": "30s"
  }
}
EOF
    
    # Create ML-specific dashboard
    cat > "$MONITORING_DIR/grafana/dashboards/ml-monitoring.json" << 'EOF'
{
  "dashboard": {
    "id": null,
    "title": "ML Worker Monitoring",
    "tags": ["wwtp", "ml", "worker"],
    "timezone": "browser",
    "panels": [
      {
        "id": 1,
        "title": "Model Status",
        "type": "stat",
        "gridPos": {"h": 4, "w": 6, "x": 0, "y": 0},
        "targets": [
          {
            "expr": "ml_model_status",
            "refId": "A"
          }
        ]
      },
      {
        "id": 2,
        "title": "Images Processed",
        "type": "stat",
        "gridPos": {"h": 4, "w": 6, "x": 6, "y": 0},
        "targets": [
          {
            "expr": "increase(ml_images_processed_total[1h])",
            "refId": "A"
          }
        ]
      },
      {
        "id": 3,
        "title": "Anomalies Detected",
        "type": "stat",
        "gridPos": {"h": 4, "w": 6, "x": 12, "y": 0},
        "targets": [
          {
            "expr": "increase(ml_anomalies_detected_total[1h])",
            "refId": "A"
          }
        ]
      },
      {
        "id": 4,
        "title": "Processing Errors",
        "type": "stat",
        "gridPos": {"h": 4, "w": 6, "x": 18, "y": 0},
        "targets": [
          {
            "expr": "increase(ml_queue_processing_errors_total[1h])",
            "refId": "A"
          }
        ]
      }
    ],
    "time": {
      "from": "now-6h",
      "to": "now"
    },
    "refresh": "1m"
  }
}
EOF
    
    log_success "Grafana dashboards configured"
}

setup_exporters() {
    log_info "Setting up additional exporters..."
    
    # Create docker-compose for exporters
    cat > "$PROJECT_DIR/docker-compose.exporters.yml" << EOF
version: '3.8'

services:
  # Node Exporter for system metrics
  node-exporter:
    image: prom/node-exporter:latest
    container_name: wwtp_node_exporter
    restart: always
    command:
      - '--path.procfs=/host/proc'
      - '--path.rootfs=/rootfs'
      - '--path.sysfs=/host/sys'
      - '--collector.filesystem.ignored-mount-points=^/(sys|proc|dev|host|etc)($$|/)'
    volumes:
      - /proc:/host/proc:ro
      - /sys:/host/sys:ro
      - /:/rootfs:ro
    ports:
      - "9100:9100"
    networks:
      - wwtp_network

  # cAdvisor for container metrics
  cadvisor:
    image: gcr.io/cadvisor/cadvisor:latest
    container_name: wwtp_cadvisor
    restart: always
    privileged: true
    volumes:
      - /:/rootfs:ro
      - /var/run:/var/run:rw
      - /sys:/sys:ro
      - /var/lib/docker/:/var/lib/docker:ro
      - /dev/disk/:/dev/disk:ro
    ports:
      - "8080:8080"
    networks:
      - wwtp_network

  # PostgreSQL Exporter
  postgres-exporter:
    image: prometheuscommunity/postgres-exporter:latest
    container_name: wwtp_postgres_exporter
    restart: always
    environment:
      DATA_SOURCE_NAME: "postgresql://\${POSTGRES_USER}:\${POSTGRES_PASSWORD}@postgres:5432/\${POSTGRES_DB}?sslmode=disable"
    ports:
      - "9187:9187"
    networks:
      - wwtp_network
    depends_on:
      - postgres

  # Redis Exporter
  redis-exporter:
    image: oliver006/redis_exporter:latest
    container_name: wwtp_redis_exporter
    restart: always
    environment:
      REDIS_ADDR: "redis://redis:6379"
    ports:
      - "9121:9121"
    networks:
      - wwtp_network
    depends_on:
      - redis

  # Nginx Exporter
  nginx-exporter:
    image: nginx/nginx-prometheus-exporter:latest
    container_name: wwtp_nginx_exporter
    restart: always
    command:
      - -nginx.scrape-uri=http://nginx/nginx_status
    ports:
      - "9113:9113"
    networks:
      - wwtp_network
    depends_on:
      - nginx

networks:
  wwtp_network:
    external: true
EOF
    
    log_success "Exporters configuration created"
}

create_health_check_service() {
    log_info "Creating health check service..."
    
    # Create health check script
    cat > "$MONITORING_DIR/health-check.py" << 'EOF'
#!/usr/bin/env python3
import requests
import json
import time
import sys
import smtplib
from email.mime.text import MIMEText
from datetime import datetime
import os

# Configuration
SERVICES = {
    'main_app': 'http://localhost/health',
    'auth_service': 'http://localhost/api/auth/health',
    'upload_service': 'http://localhost/api/upload/health', 
    'review_service': 'http://localhost/api/review/health',
    'prometheus': 'http://localhost:9090/-/healthy',
    'grafana': 'http://localhost:3001/api/health'
}

ALERT_EMAIL = os.getenv('ALERT_EMAIL', 'admin@example.com')
SMTP_HOST = os.getenv('SMTP_HOST', 'localhost')
SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))

def check_service(name, url):
    """Check if a service is healthy"""
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return True, "OK"
        else:
            return False, f"HTTP {response.status_code}"
    except requests.exceptions.RequestException as e:
        return False, str(e)

def send_alert(subject, body):
    """Send alert email"""
    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = 'monitoring@wwtp.local'
        msg['To'] = ALERT_EMAIL
        
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"Failed to send alert: {e}")
        return False

def main():
    """Main health check function"""
    failed_services = []
    
    print(f"Health check started at {datetime.now()}")
    
    for service_name, service_url in SERVICES.items():
        is_healthy, message = check_service(service_name, service_url)
        
        if is_healthy:
            print(f"✓ {service_name}: {message}")
        else:
            print(f"✗ {service_name}: {message}")
            failed_services.append((service_name, message))
    
    if failed_services:
        print(f"\n{len(failed_services)} services are unhealthy")
        
        # Send alert
        subject = f"WWTP Health Check Alert - {len(failed_services)} services down"
        body = f"Health check failed at {datetime.now()}\n\n"
        body += "Failed services:\n"
        for service, error in failed_services:
            body += f"- {service}: {error}\n"
        
        if send_alert(subject, body):
            print("Alert email sent")
        
        sys.exit(1)
    else:
        print("\nAll services are healthy")
        sys.exit(0)

if __name__ == '__main__':
    main()
EOF
    
    chmod +x "$MONITORING_DIR/health-check.py"
    
    # Create systemd service for health checks
    cat > /etc/systemd/system/wwtp-health-check.service << EOF
[Unit]
Description=WWTP Health Check Service
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 $MONITORING_DIR/health-check.py
User=monitoring
Group=monitoring
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
    
    # Create systemd timer
    cat > /etc/systemd/system/wwtp-health-check.timer << EOF
[Unit]
Description=Run WWTP Health Check every 5 minutes
Requires=wwtp-health-check.service

[Timer]
OnBootSec=5min
OnUnitActiveSec=5min

[Install]
WantedBy=timers.target
EOF
    
    # Create monitoring user
    useradd -r -s /bin/false monitoring || true
    
    # Enable and start timer
    systemctl daemon-reload
    systemctl enable wwtp-health-check.timer
    systemctl start wwtp-health-check.timer
    
    log_success "Health check service configured"
}

setup_log_aggregation() {
    log_info "Setting up log aggregation..."
    
    # Create Fluentd configuration for log collection
    cat > "$PROJECT_DIR/docker-compose.logging.yml" << EOF
version: '3.8'

services:
  fluentd:
    image: fluent/fluentd:v1.16-debian-1
    container_name: wwtp_fluentd
    restart: always
    volumes:
      - ./infrastructure/fluentd/fluent.conf:/fluentd/etc/fluent.conf
      - /var/lib/docker/containers:/var/lib/docker/containers:ro
      - /var/log:/var/log:ro
    ports:
      - "24224:24224"
      - "24224:24224/udp"
    networks:
      - wwtp_network

  elasticsearch:
    image: docker.elastic.co/elasticsearch/elasticsearch:8.11.0
    container_name: wwtp_elasticsearch
    restart: always
    environment:
      - discovery.type=single-node
      - xpack.security.enabled=false
      - "ES_JAVA_OPTS=-Xms512m -Xmx512m"
    volumes:
      - elasticsearch_data:/usr/share/elasticsearch/data
    ports:
      - "9200:9200"
    networks:
      - wwtp_network

  kibana:
    image: docker.elastic.co/kibana/kibana:8.11.0
    container_name: wwtp_kibana
    restart: always
    environment:
      ELASTICSEARCH_HOSTS: http://elasticsearch:9200
    ports:
      - "5601:5601"
    networks:
      - wwtp_network
    depends_on:
      - elasticsearch

volumes:
  elasticsearch_data:

networks:
  wwtp_network:
    external: true
EOF
    
    # Create Fluentd configuration
    mkdir -p "$PROJECT_DIR/infrastructure/fluentd"
    cat > "$PROJECT_DIR/infrastructure/fluentd/fluent.conf" << 'EOF'
<source>
  @type forward
  port 24224
  bind 0.0.0.0
</source>

<source>
  @type tail
  path /var/log/wwtp-anomaly/*.log
  pos_file /var/log/fluentd-wwtp.log.pos
  tag wwtp.*
  <parse>
    @type json
    time_key timestamp
    time_format %Y-%m-%dT%H:%M:%S.%L%z
  </parse>
</source>

<match wwtp.*>
  @type elasticsearch
  host elasticsearch
  port 9200
  logstash_format true
  logstash_prefix wwtp
  <buffer>
    flush_interval 10s
  </buffer>
</match>
EOF
    
    log_success "Log aggregation configured"
}

start_monitoring_stack() {
    log_info "Starting monitoring stack..."
    
    cd "$PROJECT_DIR"
    
    # Start exporters
    docker-compose -f docker-compose.exporters.yml up -d
    
    # Start main monitoring services
    docker-compose up -d prometheus grafana
    
    if [ -f "docker-compose.logging.yml" ]; then
        docker-compose -f docker-compose.logging.yml up -d
    fi
    
    # Wait for services to start
    sleep 30
    
    log_success "Monitoring stack started"
}

create_monitoring_summary() {
    log_success "Monitoring setup completed!"
    echo
    echo "================== MONITORING SUMMARY =================="
    echo "Monitoring Directory: $MONITORING_DIR"
    echo
    echo "Services:"
    echo "  Prometheus:         http://localhost:9090"
    echo "  Grafana:           http://localhost:3001 (admin/admin123)"
    echo "  Alertmanager:      http://localhost:9093"
    echo "  Node Exporter:     http://localhost:9100/metrics"
    echo "  cAdvisor:          http://localhost:8080"
    echo
    if [ -f "$PROJECT_DIR/docker-compose.logging.yml" ]; then
    echo "Logging:"
    echo "  Kibana:            http://localhost:5601"
    echo "  Elasticsearch:     http://localhost:9200"
    echo
    fi
    echo "Health Checks:"
    echo "  Manual check:      python3 $MONITORING_DIR/health-check.py"
    echo "  Service status:    systemctl status wwtp-health-check.timer"
    echo "  View logs:         journalctl -u wwtp-health-check.service"
    echo
    echo "Alerts:"
    echo "  Email alerts:      $ALERT_EMAIL"
    if [ -n "$SLACK_WEBHOOK" ]; then
    echo "  Slack alerts:      Configured"
    fi
    echo
    echo "Management:"
    echo "  Start monitoring:  docker-compose up -d prometheus grafana"
    echo "  Stop monitoring:   docker-compose down"
    echo "  View logs:         docker-compose logs -f"
    echo "  Restart services:  systemctl restart wwtp-health-check.timer"
    echo
    echo "Next Steps:"
    echo "1. Import Grafana dashboards"
    echo "2. Configure alert notification channels"
    echo "3. Set up log retention policies"
    echo "4. Configure backup monitoring"
    echo "5. Test alert notifications"
    echo "========================================================="
}

# Main execution
main() {
    log_info "Starting WWTP monitoring setup..."
    
    if [ "$EUID" -ne 0 ]; then
        log_error "This script must be run as root for system-level setup"
        exit 1
    fi
    
    create_monitoring_directories
    setup_prometheus_config
    setup_alertmanager
    setup_grafana_dashboards
    setup_exporters
    create_health_check_service
    
    if [ "${1:-}" = "--with-logging" ]; then
        setup_log_aggregation
    fi
    
    start_monitoring_stack
    create_monitoring_summary
}

# Run main function
main "$@"