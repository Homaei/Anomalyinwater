#!/bin/bash

# WWTP Anomaly Detection System - Database Migration Script
# This script handles database migrations and maintenance

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/wwtp-anomaly}"
DB_CONTAINER="wwtp_postgres"
DB_NAME="${POSTGRES_DB:-wwtp_anomaly}"
DB_USER="${POSTGRES_USER:-wwtp_user}"

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

check_database_connection() {
    log_info "Checking database connection..."
    
    if ! docker exec "$DB_CONTAINER" pg_isready -U "$DB_USER" -d "$DB_NAME" >/dev/null 2>&1; then
        log_error "Cannot connect to database. Is the container running?"
        exit 1
    fi
    
    log_success "Database connection successful"
}

backup_database() {
    log_info "Creating database backup..."
    
    timestamp=$(date +"%Y%m%d_%H%M%S")
    backup_file="$BACKUP_DIR/db_backup_$timestamp.sql"
    
    # Create backup directory if it doesn't exist
    mkdir -p "$BACKUP_DIR"
    
    # Create database backup
    docker exec "$DB_CONTAINER" pg_dump -U "$DB_USER" -d "$DB_NAME" > "$backup_file"
    
    # Compress backup
    gzip "$backup_file"
    
    log_success "Database backup created: ${backup_file}.gz"
    
    # Keep only last 7 backups
    find "$BACKUP_DIR" -name "db_backup_*.sql.gz" -type f -mtime +7 -delete
}

restore_database() {
    local backup_file="$1"
    
    if [ -z "$backup_file" ]; then
        log_error "Backup file not specified"
        exit 1
    fi
    
    if [ ! -f "$backup_file" ]; then
        log_error "Backup file not found: $backup_file"
        exit 1
    fi
    
    log_warning "This will completely replace the current database!"
    read -p "Are you sure you want to continue? (yes/no): " confirm
    
    if [ "$confirm" != "yes" ]; then
        log_info "Database restore cancelled"
        exit 0
    fi
    
    log_info "Restoring database from: $backup_file"
    
    # Create a backup before restore
    backup_database
    
    # Drop and recreate database
    docker exec "$DB_CONTAINER" psql -U "$DB_USER" -c "DROP DATABASE IF EXISTS $DB_NAME;"
    docker exec "$DB_CONTAINER" psql -U "$DB_USER" -c "CREATE DATABASE $DB_NAME;"
    
    # Restore from backup
    if [[ "$backup_file" == *.gz ]]; then
        zcat "$backup_file" | docker exec -i "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME"
    else
        docker exec -i "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" < "$backup_file"
    fi
    
    log_success "Database restored successfully"
}

run_migrations() {
    log_info "Running database migrations..."
    
    # Backup before migration
    backup_database
    
    # Run migrations for each service
    services=("auth-service" "upload-service" "review-service")
    
    for service in "${services[@]}"; do
        if [ -d "$PROJECT_DIR/backend/$service/migrations" ]; then
            log_info "Running migrations for $service..."
            
            # Run Alembic migrations
            docker exec "wwtp_${service//-/_}" alembic upgrade head
            
            log_success "Migrations completed for $service"
        else
            log_info "No migrations found for $service"
        fi
    done
    
    log_success "All migrations completed"
}

create_migration() {
    local service="$1"
    local message="$2"
    
    if [ -z "$service" ] || [ -z "$message" ]; then
        log_error "Usage: create_migration <service> <message>"
        exit 1
    fi
    
    if [ ! -d "$PROJECT_DIR/backend/$service" ]; then
        log_error "Service not found: $service"
        exit 1
    fi
    
    log_info "Creating migration for $service: $message"
    
    # Create migration
    docker exec "wwtp_${service//-/_}" alembic revision --autogenerate -m "$message"
    
    log_success "Migration created for $service"
    log_info "Don't forget to review the generated migration file!"
}

init_database() {
    log_info "Initializing database..."
    
    # Run initialization script
    if [ -f "$PROJECT_DIR/infrastructure/postgres/init.sql" ]; then
        docker exec -i "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" < "$PROJECT_DIR/infrastructure/postgres/init.sql"
        log_success "Database initialized with schema"
    fi
    
    # Create Alembic version tables
    services=("auth-service" "upload-service" "review-service")
    
    for service in "${services[@]}"; do
        if [ -d "$PROJECT_DIR/backend/$service/migrations" ]; then
            log_info "Initializing Alembic for $service..."
            docker exec "wwtp_${service//-/_}" alembic stamp head
        fi
    done
    
    log_success "Database initialization completed"
}

reset_database() {
    log_warning "This will completely reset the database!"
    read -p "Are you sure you want to continue? (yes/no): " confirm
    
    if [ "$confirm" != "yes" ]; then
        log_info "Database reset cancelled"
        exit 0
    fi
    
    log_info "Resetting database..."
    
    # Create final backup
    backup_database
    
    # Drop and recreate database
    docker exec "$DB_CONTAINER" psql -U "$DB_USER" -c "DROP DATABASE IF EXISTS $DB_NAME;"
    docker exec "$DB_CONTAINER" psql -U "$DB_USER" -c "CREATE DATABASE $DB_NAME;"
    
    # Reinitialize
    init_database
    
    log_success "Database reset completed"
}

check_database_health() {
    log_info "Checking database health..."
    
    # Check connection
    check_database_connection
    
    # Check database size
    db_size=$(docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT pg_size_pretty(pg_database_size('$DB_NAME'));")
    log_info "Database size: $db_size"
    
    # Check table counts
    tables=$(docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT schemaname,tablename,n_tup_ins,n_tup_upd,n_tup_del FROM pg_stat_user_tables ORDER BY schemaname,tablename;")
    
    echo
    echo "Table Statistics:"
    echo "Schema | Table | Inserts | Updates | Deletes"
    echo "-------|-------|---------|---------|--------"
    echo "$tables"
    
    # Check for long-running queries
    long_queries=$(docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT pid, now() - pg_stat_activity.query_start AS duration, query FROM pg_stat_activity WHERE (now() - pg_stat_activity.query_start) > interval '5 minutes' AND state = 'active';")
    
    if [ -n "$long_queries" ]; then
        log_warning "Long-running queries detected:"
        echo "$long_queries"
    else
        log_success "No long-running queries found"
    fi
    
    # Check for bloat
    bloat=$(docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT schemaname, tablename, attname, n_distinct, correlation FROM pg_stats WHERE schemaname = 'public' ORDER BY n_distinct DESC LIMIT 10;")
    
    echo
    echo "Top 10 columns by distinct values:"
    echo "$bloat"
    
    log_success "Database health check completed"
}

vacuum_database() {
    log_info "Running database maintenance (VACUUM)..."
    
    # Run VACUUM ANALYZE on all tables
    docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -c "VACUUM ANALYZE;"
    
    log_success "Database vacuum completed"
}

optimize_database() {
    log_info "Optimizing database performance..."
    
    # Update table statistics
    docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -c "ANALYZE;"
    
    # Reindex tables
    docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -c "REINDEX DATABASE $DB_NAME;"
    
    # Vacuum full (WARNING: This locks tables)
    read -p "Run VACUUM FULL? This will lock tables temporarily. (yes/no): " confirm
    if [ "$confirm" = "yes" ]; then
        docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -c "VACUUM FULL;"
        log_success "Full vacuum completed"
    fi
    
    log_success "Database optimization completed"
}

show_database_info() {
    log_info "Database Information:"
    
    # Database version
    version=$(docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT version();")
    echo "Version: $version"
    
    # Database size
    db_size=$(docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT pg_size_pretty(pg_database_size('$DB_NAME'));")
    echo "Size: $db_size"
    
    # Connection info
    connections=$(docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT count(*) FROM pg_stat_activity WHERE datname='$DB_NAME';")
    max_connections=$(docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -t -c "SHOW max_connections;")
    echo "Connections: $connections / $max_connections"
    
    # Tables
    table_count=$(docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';")
    echo "Tables: $table_count"
    
    # Recent backups
    echo
    echo "Recent backups:"
    if [ -d "$BACKUP_DIR" ]; then
        ls -lah "$BACKUP_DIR"/db_backup_*.sql.gz 2>/dev/null | tail -5 || echo "No backups found"
    else
        echo "No backup directory found"
    fi
}

# Usage function
usage() {
    echo "Usage: $0 <command> [options]"
    echo
    echo "Commands:"
    echo "  backup                    - Create database backup"
    echo "  restore <backup_file>     - Restore database from backup"
    echo "  migrate                   - Run pending migrations"
    echo "  init                      - Initialize database schema"
    echo "  reset                     - Reset database (WARNING: destructive)"
    echo "  health                    - Check database health"
    echo "  vacuum                    - Run database vacuum"
    echo "  optimize                  - Optimize database performance"
    echo "  info                      - Show database information"
    echo "  create-migration <service> <message> - Create new migration"
    echo
    echo "Examples:"
    echo "  $0 backup"
    echo "  $0 restore /var/backups/wwtp-anomaly/db_backup_20231201_120000.sql.gz"
    echo "  $0 create-migration auth-service 'add user preferences table'"
    echo "  $0 migrate"
    echo "  $0 health"
}

# Main execution
main() {
    cd "$PROJECT_DIR"
    
    # Load environment variables
    if [ -f ".env" ]; then
        source .env
    fi
    
    case "$1" in
        backup)
            check_database_connection
            backup_database
            ;;
        restore)
            check_database_connection
            restore_database "$2"
            ;;
        migrate)
            check_database_connection
            run_migrations
            ;;
        init)
            check_database_connection
            init_database
            ;;
        reset)
            check_database_connection
            reset_database
            ;;
        health)
            check_database_health
            ;;
        vacuum)
            check_database_connection
            vacuum_database
            ;;
        optimize)
            check_database_connection
            optimize_database
            ;;
        info)
            check_database_connection
            show_database_info
            ;;
        create-migration)
            create_migration "$2" "$3"
            ;;
        *)
            usage
            exit 1
            ;;
    esac
}

# Run main function
main "$@"