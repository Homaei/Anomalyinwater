#!/bin/bash

# WWTP Anomaly Detection System - Production Deployment Script
# This script deploys the application to production environment

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROJECT_NAME="wwtp-anomaly-detection"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEPLOY_ENV="${DEPLOY_ENV:-production}"
BACKUP_DIR="/var/backups/wwtp-anomaly"
LOG_DIR="/var/log/wwtp-anomaly"

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

check_production_prerequisites() {
    log_info "Checking production prerequisites..."
    
    # Check if running as root (needed for system-level changes)
    if [ "$EUID" -ne 0 ]; then
        log_error "This script must be run as root for production deployment"
        exit 1
    fi
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed. Please install Docker first."
        exit 1
    fi
    
    # Check Docker Compose
    if ! command -v docker-compose &> /dev/null; then
        log_error "Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi
    
    # Check if production environment file exists
    if [ ! -f "$PROJECT_DIR/.env.production" ]; then
        log_error "Production environment file (.env.production) not found."
        log_error "Please create it with production configurations."
        exit 1
    fi
    
    # Check system resources
    total_memory=$(free -m | awk 'NR==2{printf "%.0f", $2}')
    if [ "$total_memory" -lt 4096 ]; then
        log_warning "System has less than 4GB RAM. Consider upgrading for better performance."
    fi
    
    available_space=$(df / | awk 'NR==2{print $4}')
    if [ "$available_space" -lt 20971520 ]; then  # 20GB in KB
        log_warning "Less than 20GB disk space available. Consider freeing up space."
    fi
    
    log_success "Prerequisites check completed"
}

setup_production_directories() {
    log_info "Setting up production directories..."
    
    # Create necessary directories
    mkdir -p "$BACKUP_DIR"
    mkdir -p "$LOG_DIR"
    mkdir -p /var/lib/wwtp-anomaly/{uploads,models,ssl}
    mkdir -p /etc/wwtp-anomaly
    
    # Set permissions
    chown -R 1001:1001 /var/lib/wwtp-anomaly
    chown -R 1001:1001 "$LOG_DIR"
    
    log_success "Production directories created"
}

backup_existing_deployment() {
    log_info "Creating backup of existing deployment..."
    
    if [ -d "/opt/wwtp-anomaly" ]; then
        timestamp=$(date +"%Y%m%d_%H%M%S")
        backup_path="$BACKUP_DIR/wwtp-anomaly-backup-$timestamp"
        
        # Backup application
        cp -r "/opt/wwtp-anomaly" "$backup_path"
        
        # Backup database
        if docker ps | grep -q wwtp_postgres; then
            log_info "Creating database backup..."
            docker exec wwtp_postgres pg_dump -U wwtp_user wwtp_anomaly > "$backup_path/database_backup.sql"
        fi
        
        # Backup volumes
        docker run --rm -v postgres_data:/data -v "$backup_path:/backup" alpine tar czf /backup/postgres_data.tar.gz -C /data .
        docker run --rm -v upload_storage:/data -v "$backup_path:/backup" alpine tar czf /backup/upload_storage.tar.gz -C /data .
        docker run --rm -v ml_models:/data -v "$backup_path:/backup" alpine tar czf /backup/ml_models.tar.gz -C /data .
        
        log_success "Backup created at: $backup_path"
    else
        log_info "No existing deployment found, skipping backup"
    fi
}

deploy_application() {
    log_info "Deploying application..."
    
    # Copy application to production directory
    if [ -d "/opt/wwtp-anomaly" ]; then
        rm -rf "/opt/wwtp-anomaly"
    fi
    
    cp -r "$PROJECT_DIR" "/opt/wwtp-anomaly"
    cd "/opt/wwtp-anomaly"
    
    # Copy production environment
    cp .env.production .env
    
    # Set proper permissions
    chown -R 1001:1001 /opt/wwtp-anomaly
    chmod +x scripts/*.sh
    
    # Build production images
    log_info "Building production Docker images..."
    docker-compose -f docker-compose.yml -f docker-compose.prod.yml build --no-cache
    
    log_success "Application deployed to /opt/wwtp-anomaly"
}

setup_ssl_certificates() {
    log_info "Setting up SSL certificates..."
    
    # Check if Let's Encrypt certificates exist
    if [ ! -f "/etc/letsencrypt/live/$(hostname)/fullchain.pem" ]; then
        log_warning "SSL certificates not found. Setting up self-signed certificates for now."
        
        # Create self-signed certificate
        openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
            -keyout /var/lib/wwtp-anomaly/ssl/key.pem \
            -out /var/lib/wwtp-anomaly/ssl/cert.pem \
            -subj "/C=US/ST=State/L=City/O=Organization/CN=$(hostname)"
        
        log_info "Self-signed certificates created. Consider setting up Let's Encrypt for production."
    else
        # Link Let's Encrypt certificates
        ln -sf "/etc/letsencrypt/live/$(hostname)/fullchain.pem" /var/lib/wwtp-anomaly/ssl/cert.pem
        ln -sf "/etc/letsencrypt/live/$(hostname)/privkey.pem" /var/lib/wwtp-anomaly/ssl/key.pem
        
        log_success "SSL certificates configured"
    fi
}

setup_systemd_services() {
    log_info "Setting up systemd services..."
    
    # Create systemd service file
    cat > /etc/systemd/system/wwtp-anomaly.service << EOF
[Unit]
Description=WWTP Anomaly Detection System
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/wwtp-anomaly
ExecStart=/usr/local/bin/docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
ExecStop=/usr/local/bin/docker-compose -f docker-compose.yml -f docker-compose.prod.yml down
TimeoutStartSec=0
User=root

[Install]
WantedBy=multi-user.target
EOF
    
    # Reload systemd and enable service
    systemctl daemon-reload
    systemctl enable wwtp-anomaly.service
    
    log_success "Systemd service configured"
}

setup_monitoring_and_alerting() {
    log_info "Setting up monitoring and alerting..."
    
    cd "/opt/wwtp-anomaly"
    
    # Start monitoring stack
    docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d prometheus grafana
    
    # Configure alertmanager if available
    if [ -f "infrastructure/alertmanager/alertmanager.yml" ]; then
        docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d alertmanager
    fi
    
    # Setup log rotation
    cat > /etc/logrotate.d/wwtp-anomaly << EOF
$LOG_DIR/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 644 1001 1001
    postrotate
        docker kill --signal="USR1" \$(docker ps --filter name=wwtp_ --format "{{.Names}}") 2>/dev/null || true
    endscript
}
EOF
    
    log_success "Monitoring and alerting configured"
}

setup_firewall() {
    log_info "Configuring firewall..."
    
    # Install ufw if not present
    if ! command -v ufw &> /dev/null; then
        apt-get update && apt-get install -y ufw
    fi
    
    # Reset firewall rules
    ufw --force reset
    
    # Default policies
    ufw default deny incoming
    ufw default allow outgoing
    
    # Allow SSH
    ufw allow ssh
    
    # Allow HTTP and HTTPS
    ufw allow 80/tcp
    ufw allow 443/tcp
    
    # Allow monitoring ports (restrict to local network)
    ufw allow from 10.0.0.0/8 to any port 9090  # Prometheus
    ufw allow from 10.0.0.0/8 to any port 3001  # Grafana
    ufw allow from 172.16.0.0/12 to any port 9090
    ufw allow from 172.16.0.0/12 to any port 3001
    ufw allow from 192.168.0.0/16 to any port 9090
    ufw allow from 192.168.0.0/16 to any port 3001
    
    # Enable firewall
    ufw --force enable
    
    log_success "Firewall configured"
}

perform_health_checks() {
    log_info "Performing health checks..."
    
    cd "/opt/wwtp-anomaly"
    
    # Wait for services to start
    sleep 30
    
    # Check if containers are running
    if ! docker-compose -f docker-compose.yml -f docker-compose.prod.yml ps | grep -q "Up"; then
        log_error "Some services failed to start"
        docker-compose -f docker-compose.yml -f docker-compose.prod.yml logs
        exit 1
    fi
    
    # Health check endpoints
    services=(
        "http://localhost/health"
        "http://localhost/api/auth/health"
        "http://localhost/api/upload/health"
        "http://localhost/api/review/health"
    )
    
    for service in "${services[@]}"; do
        log_info "Checking $service..."
        if curl -f -s "$service" >/dev/null; then
            log_success "$service is healthy"
        else
            log_error "$service is not responding"
        fi
    done
    
    # Check database connection
    if docker exec wwtp_postgres pg_isready -U wwtp_user >/dev/null 2>&1; then
        log_success "Database is accessible"
    else
        log_error "Database is not accessible"
    fi
    
    # Check RabbitMQ
    if docker exec wwtp_rabbitmq rabbitmqctl status >/dev/null 2>&1; then
        log_success "RabbitMQ is running"
    else
        log_error "RabbitMQ is not running"
    fi
    
    log_success "Health checks completed"
}

start_services() {
    log_info "Starting production services..."
    
    cd "/opt/wwtp-anomaly"
    
    # Start all services
    docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
    
    # Start systemd service
    systemctl start wwtp-anomaly.service
    
    log_success "Production services started"
}

create_production_compose() {
    log_info "Creating production docker-compose override..."
    
    cat > "$PROJECT_DIR/docker-compose.prod.yml" << EOF
version: '3.8'

services:
  auth-service:
    restart: always
    environment:
      - ENVIRONMENT=production
      - DEBUG=false
      - LOG_LEVEL=INFO
    volumes:
      - $LOG_DIR/auth-service:/app/logs

  upload-service:
    restart: always
    environment:
      - ENVIRONMENT=production
      - DEBUG=false
      - LOG_LEVEL=INFO
    volumes:
      - $LOG_DIR/upload-service:/app/logs
      - /var/lib/wwtp-anomaly/uploads:/app/uploads

  review-service:
    restart: always
    environment:
      - ENVIRONMENT=production
      - DEBUG=false
      - LOG_LEVEL=INFO
    volumes:
      - $LOG_DIR/review-service:/app/logs

  ml-worker:
    restart: always
    environment:
      - ENVIRONMENT=production
      - DEBUG=false
      - LOG_LEVEL=INFO
    volumes:
      - $LOG_DIR/ml-worker:/app/logs
      - /var/lib/wwtp-anomaly/models:/app/models
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]

  nginx:
    restart: always
    volumes:
      - /var/lib/wwtp-anomaly/ssl:/etc/nginx/ssl:ro
    ports:
      - "80:80"
      - "443:443"

  postgres:
    restart: always
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - $BACKUP_DIR:/backup

  prometheus:
    restart: always
    volumes:
      - prometheus_data:/prometheus
      - $LOG_DIR/prometheus:/var/log/prometheus

  grafana:
    restart: always
    volumes:
      - grafana_data:/var/lib/grafana
      - $LOG_DIR/grafana:/var/log/grafana

  # Add exporters for production monitoring
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
EOF
    
    log_success "Production compose file created"
}

print_deployment_summary() {
    log_success "Production deployment completed!"
    echo
    echo "================== DEPLOYMENT SUMMARY =================="
    echo "Environment:        $DEPLOY_ENV"
    echo "Application Path:   /opt/wwtp-anomaly"
    echo "Backup Directory:   $BACKUP_DIR"
    echo "Log Directory:      $LOG_DIR"
    echo
    echo "Services:"
    echo "  Main Application:   https://$(hostname)"
    echo "  Grafana Dashboard:  https://$(hostname):3001"
    echo "  Prometheus:         https://$(hostname):9090"
    echo "  RabbitMQ Mgmt:      https://$(hostname):15672"
    echo
    echo "System Commands:"
    echo "  Start services:     systemctl start wwtp-anomaly"
    echo "  Stop services:      systemctl stop wwtp-anomaly"
    echo "  View status:        systemctl status wwtp-anomaly"
    echo "  View logs:          docker-compose logs -f"
    echo
    echo "Monitoring:"
    echo "  Service logs:       $LOG_DIR/"
    echo "  Health checks:      curl https://$(hostname)/health"
    echo "  Container status:   docker ps"
    echo
    echo "Maintenance:"
    echo "  Update application: Re-run this script"
    echo "  Database backup:    ./scripts/backup.sh"
    echo "  View metrics:       https://$(hostname):3001"
    echo
    echo "Next Steps:"
    echo "1. Configure SSL certificates (Let's Encrypt recommended)"
    echo "2. Set up monitoring alerts"
    echo "3. Configure automated backups"
    echo "4. Review security settings"
    echo "5. Set up log aggregation"
    echo "========================================================="
}

# Main execution
main() {
    log_info "Starting WWTP Anomaly Detection System production deployment..."
    
    check_production_prerequisites
    setup_production_directories
    backup_existing_deployment
    create_production_compose
    deploy_application
    setup_ssl_certificates
    setup_systemd_services
    setup_firewall
    setup_monitoring_and_alerting
    start_services
    perform_health_checks
    
    print_deployment_summary
}

# Run main function with environment
DEPLOY_ENV="${1:-production}"
main