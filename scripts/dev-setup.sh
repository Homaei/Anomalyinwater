#!/bin/bash

# WWTP Anomaly Detection System - Development Setup Script
# This script sets up the development environment

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

check_prerequisites() {
    log_info "Checking prerequisites..."
    
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
    
    # Check Node.js (for frontend development)
    if ! command -v node &> /dev/null; then
        log_warning "Node.js is not installed. Frontend development will be limited."
    fi
    
    # Check Python (for backend development)
    if ! command -v python3 &> /dev/null; then
        log_warning "Python 3 is not installed. Backend development will be limited."
    fi
    
    # Check git
    if ! command -v git &> /dev/null; then
        log_warning "Git is not installed. Version control will be limited."
    fi
    
    log_success "Prerequisites check completed"
}

create_environment_files() {
    log_info "Creating environment configuration files..."
    
    # Create .env file if it doesn't exist
    if [ ! -f "$PROJECT_DIR/.env" ]; then
        cat > "$PROJECT_DIR/.env" << EOF
# Database Configuration
POSTGRES_USER=wwtp_user
POSTGRES_PASSWORD=secure_password
POSTGRES_DB=wwtp_anomaly

# JWT Configuration
JWT_SECRET=your_jwt_secret_key_change_in_production
JWT_ALGORITHM=HS256
JWT_EXPIRATION=3600

# RabbitMQ Configuration
RABBITMQ_USER=admin
RABBITMQ_PASSWORD=admin123

# MinIO Configuration
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin

# Redis Configuration
REDIS_PASSWORD=redis_password

# Grafana Configuration
GRAFANA_PASSWORD=admin123

# Environment
ENVIRONMENT=development
DEBUG=true
LOG_LEVEL=DEBUG

# API URLs
REACT_APP_API_URL=http://localhost/api
REACT_APP_WS_URL=ws://localhost/ws

# ML Configuration
MODEL_VERSION=1.0.0
ANOMALY_THRESHOLD=0.7
CONFIDENCE_THRESHOLD=0.5
USE_GPU=true
EOF
        log_success "Created .env file"
    else
        log_info ".env file already exists"
    fi
    
    # Create .env.test for testing
    if [ ! -f "$PROJECT_DIR/.env.test" ]; then
        cat > "$PROJECT_DIR/.env.test" << EOF
# Test Environment Configuration
TESTING=true
POSTGRES_USER=test_user
POSTGRES_PASSWORD=test_password
POSTGRES_DB=test_wwtp_anomaly
JWT_SECRET=test_jwt_secret
RABBITMQ_USER=test
RABBITMQ_PASSWORD=test
REDIS_PASSWORD=test_redis
DEBUG=true
LOG_LEVEL=DEBUG
METRICS_ENABLED=false
EOF
        log_success "Created .env.test file"
    else
        log_info ".env.test file already exists"
    fi
}

setup_docker_environment() {
    log_info "Setting up Docker environment..."
    
    cd "$PROJECT_DIR"
    
    # Pull base images
    log_info "Pulling Docker base images..."
    docker pull postgres:15-alpine
    docker pull redis:7-alpine
    docker pull rabbitmq:3.12-management-alpine
    docker pull nginx:alpine
    docker pull prom/prometheus:latest
    docker pull grafana/grafana:latest
    docker pull minio/minio:latest
    docker pull python:3.11-slim
    docker pull node:18-alpine
    docker pull nvidia/cuda:11.8-runtime-ubuntu22.04
    
    # Create Docker network
    if ! docker network ls | grep -q wwtp_network; then
        docker network create wwtp_network
        log_success "Created Docker network: wwtp_network"
    else
        log_info "Docker network wwtp_network already exists"
    fi
    
    # Create volumes
    log_info "Creating Docker volumes..."
    docker volume create postgres_data || true
    docker volume create rabbitmq_data || true
    docker volume create redis_data || true
    docker volume create minio_data || true
    docker volume create upload_storage || true
    docker volume create ml_models || true
    docker volume create prometheus_data || true
    docker volume create grafana_data || true
    
    log_success "Docker environment setup completed"
}

setup_backend_development() {
    log_info "Setting up backend development environment..."
    
    cd "$PROJECT_DIR"
    
    # Create Python virtual environment for each service
    services=("auth-service" "upload-service" "review-service" "ml-worker")
    
    for service in "${services[@]}"; do
        service_dir="backend/$service"
        if [ -d "$service_dir" ]; then
            log_info "Setting up $service..."
            
            cd "$PROJECT_DIR/$service_dir"
            
            # Create virtual environment
            if [ ! -d "venv" ]; then
                python3 -m venv venv
                log_success "Created virtual environment for $service"
            fi
            
            # Activate virtual environment and install dependencies
            source venv/bin/activate
            if [ -f "requirements.txt" ]; then
                pip install --upgrade pip
                pip install -r requirements.txt
                pip install pytest pytest-asyncio pytest-cov black flake8 mypy
                log_success "Installed dependencies for $service"
            fi
            deactivate
            
            cd "$PROJECT_DIR"
        fi
    done
    
    log_success "Backend development environment setup completed"
}

setup_frontend_development() {
    log_info "Setting up frontend development environment..."
    
    cd "$PROJECT_DIR/frontend"
    
    if command -v node &> /dev/null; then
        # Install dependencies
        if [ -f "package.json" ]; then
            npm install
            log_success "Installed frontend dependencies"
        fi
    else
        log_warning "Node.js not available, skipping frontend setup"
    fi
    
    cd "$PROJECT_DIR"
}

setup_testing_environment() {
    log_info "Setting up testing environment..."
    
    cd "$PROJECT_DIR"
    
    # Create test database
    log_info "Setting up test database..."
    
    # Create pytest configuration
    if [ ! -f "pytest.ini" ]; then
        cat > "pytest.ini" << EOF
[tool:pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = 
    -v
    --tb=short
    --strict-markers
    --strict-config
    --cov=backend
    --cov-report=term-missing
    --cov-report=html:htmlcov
    --cov-fail-under=80

markers =
    slow: mark test as slow running
    integration: mark test as integration test
    unit: mark test as unit test
    performance: mark test as performance test

filterwarnings =
    ignore::DeprecationWarning
    ignore::PendingDeprecationWarning
EOF
        log_success "Created pytest configuration"
    fi
    
    # Create pre-commit configuration
    if [ ! -f ".pre-commit-config.yaml" ]; then
        cat > ".pre-commit-config.yaml" << EOF
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.4.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
      - id: check-merge-conflict
  
  - repo: https://github.com/psf/black
    rev: 23.3.0
    hooks:
      - id: black
        language_version: python3
  
  - repo: https://github.com/pycqa/flake8
    rev: 6.0.0
    hooks:
      - id: flake8
        additional_dependencies: [flake8-docstrings]
  
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.3.0
    hooks:
      - id: mypy
        additional_dependencies: [types-all]
EOF
        log_success "Created pre-commit configuration"
    fi
    
    log_success "Testing environment setup completed"
}

create_development_scripts() {
    log_info "Creating development helper scripts..."
    
    mkdir -p "$PROJECT_DIR/scripts/dev"
    
    # Create service management script
    cat > "$PROJECT_DIR/scripts/dev/services.sh" << 'EOF'
#!/bin/bash

# Service management script

case "$1" in
    start)
        echo "Starting development services..."
        docker-compose up -d postgres redis rabbitmq minio
        ;;
    stop)
        echo "Stopping development services..."
        docker-compose down
        ;;
    restart)
        echo "Restarting development services..."
        docker-compose restart
        ;;
    logs)
        docker-compose logs -f ${2:-}
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|logs [service]}"
        exit 1
        ;;
esac
EOF
    
    chmod +x "$PROJECT_DIR/scripts/dev/services.sh"
    
    # Create test runner script
    cat > "$PROJECT_DIR/scripts/dev/test.sh" << 'EOF'
#!/bin/bash

# Test runner script

case "$1" in
    backend)
        echo "Running backend tests..."
        cd "$(dirname "$0")/../.."
        python -m pytest tests/backend/ -v
        ;;
    frontend)
        echo "Running frontend tests..."
        cd "$(dirname "$0")/../../frontend"
        npm test
        ;;
    integration)
        echo "Running integration tests..."
        cd "$(dirname "$0")/../.."
        python -m pytest tests/integration/ -v -m integration
        ;;
    all)
        echo "Running all tests..."
        $0 backend
        $0 frontend
        $0 integration
        ;;
    *)
        echo "Usage: $0 {backend|frontend|integration|all}"
        exit 1
        ;;
esac
EOF
    
    chmod +x "$PROJECT_DIR/scripts/dev/test.sh"
    
    log_success "Created development helper scripts"
}

setup_monitoring() {
    log_info "Setting up monitoring and observability..."
    
    cd "$PROJECT_DIR"
    
    # Start monitoring stack
    docker-compose up -d prometheus grafana
    
    # Wait for services to be ready
    sleep 10
    
    log_info "Monitoring setup completed"
    log_info "Prometheus: http://localhost:9090"
    log_info "Grafana: http://localhost:3001 (admin/admin123)"
}

print_summary() {
    log_success "Development environment setup completed!"
    echo
    echo "================== SUMMARY =================="
    echo "Project Directory: $PROJECT_DIR"
    echo
    echo "Available Commands:"
    echo "  Start services:     ./scripts/dev/services.sh start"
    echo "  Stop services:      ./scripts/dev/services.sh stop"
    echo "  View logs:          ./scripts/dev/services.sh logs [service]"
    echo "  Run tests:          ./scripts/dev/test.sh [backend|frontend|integration|all]"
    echo
    echo "Services:"
    echo "  Database:           localhost:5432"
    echo "  Redis:              localhost:6379"
    echo "  RabbitMQ:           http://localhost:15672 (admin/admin123)"
    echo "  MinIO:              http://localhost:9001 (minioadmin/minioadmin)"
    echo "  Prometheus:         http://localhost:9090"
    echo "  Grafana:            http://localhost:3001 (admin/admin123)"
    echo
    echo "Development:"
    echo "  Frontend:           cd frontend && npm start"
    echo "  Backend services:   Run individual services in their directories"
    echo
    echo "Testing:"
    echo "  Run all tests:      ./scripts/dev/test.sh all"
    echo "  Backend tests:      ./scripts/dev/test.sh backend"
    echo "  Frontend tests:     ./scripts/dev/test.sh frontend"
    echo
    echo "Next Steps:"
    echo "1. Review and update .env file with your configurations"
    echo "2. Start development services: ./scripts/dev/services.sh start"
    echo "3. Run tests to verify setup: ./scripts/dev/test.sh all"
    echo "4. Start developing!"
    echo "=============================================="
}

# Main execution
main() {
    log_info "Starting WWTP Anomaly Detection System development setup..."
    
    check_prerequisites
    create_environment_files
    setup_docker_environment
    setup_backend_development
    setup_frontend_development
    setup_testing_environment
    create_development_scripts
    
    if [ "${1:-}" = "--with-monitoring" ]; then
        setup_monitoring
    fi
    
    print_summary
}

# Run main function
main "$@"