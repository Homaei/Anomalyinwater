-- WWTP Anomaly Detection Database Schema
-- Create database and extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Users table for authentication
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    role VARCHAR(20) DEFAULT 'operator' CHECK (role IN ('admin', 'reviewer', 'operator')),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP WITH TIME ZONE
);

-- Images table for uploaded images
CREATE TABLE images (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    filename VARCHAR(255) NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    file_path VARCHAR(500) NOT NULL,
    file_size BIGINT NOT NULL,
    mime_type VARCHAR(100) NOT NULL,
    width INTEGER,
    height INTEGER,
    uploaded_by UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    upload_timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    processing_status VARCHAR(20) DEFAULT 'pending' CHECK (processing_status IN ('pending', 'processing', 'completed', 'failed')),
    metadata JSONB DEFAULT '{}',
    checksum VARCHAR(64) NOT NULL
);

-- Detections table for ML model predictions
CREATE TABLE detections (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    image_id UUID NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    model_version VARCHAR(50) NOT NULL,
    confidence_score FLOAT NOT NULL CHECK (confidence_score >= 0 AND confidence_score <= 1),
    is_anomaly BOOLEAN NOT NULL,
    anomaly_type VARCHAR(100),
    bounding_box JSONB, -- {x, y, width, height}
    features JSONB DEFAULT '{}',
    processing_time_ms INTEGER,
    detected_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Reviews table for human validation
CREATE TABLE reviews (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    detection_id UUID NOT NULL REFERENCES detections(id) ON DELETE CASCADE,
    reviewer_id UUID NOT NULL REFERENCES users(id),
    review_status VARCHAR(20) DEFAULT 'pending' CHECK (review_status IN ('pending', 'approved', 'rejected')),
    human_verdict VARCHAR(20) CHECK (human_verdict IN ('true_positive', 'false_positive', 'true_negative', 'false_negative')),
    confidence_level INTEGER CHECK (confidence_level >= 1 AND confidence_level <= 5),
    notes TEXT,
    reviewed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    review_duration_seconds INTEGER
);

-- Audit logs for system activity tracking
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id),
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(50) NOT NULL,
    resource_id UUID,
    details JSONB DEFAULT '{}',
    ip_address INET,
    user_agent TEXT,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- System metrics for monitoring
CREATE TABLE system_metrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    metric_name VARCHAR(100) NOT NULL,
    metric_value FLOAT NOT NULL,
    metric_type VARCHAR(20) NOT NULL CHECK (metric_type IN ('counter', 'gauge', 'histogram')),
    labels JSONB DEFAULT '{}',
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for performance
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_role ON users(role);

CREATE INDEX idx_images_uploaded_by ON images(uploaded_by);
CREATE INDEX idx_images_upload_timestamp ON images(upload_timestamp);
CREATE INDEX idx_images_processing_status ON images(processing_status);
CREATE INDEX idx_images_checksum ON images(checksum);

CREATE INDEX idx_detections_image_id ON detections(image_id);
CREATE INDEX idx_detections_is_anomaly ON detections(is_anomaly);
CREATE INDEX idx_detections_confidence_score ON detections(confidence_score);
CREATE INDEX idx_detections_detected_at ON detections(detected_at);

CREATE INDEX idx_reviews_detection_id ON reviews(detection_id);
CREATE INDEX idx_reviews_reviewer_id ON reviews(reviewer_id);
CREATE INDEX idx_reviews_review_status ON reviews(review_status);
CREATE INDEX idx_reviews_reviewed_at ON reviews(reviewed_at);

CREATE INDEX idx_audit_logs_user_id ON audit_logs(user_id);
CREATE INDEX idx_audit_logs_action ON audit_logs(action);
CREATE INDEX idx_audit_logs_timestamp ON audit_logs(timestamp);

CREATE INDEX idx_system_metrics_metric_name ON system_metrics(metric_name);
CREATE INDEX idx_system_metrics_timestamp ON system_metrics(timestamp);

-- Create triggers for updated_at timestamps
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_users_updated_at 
    BEFORE UPDATE ON users 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Create views for common queries
CREATE VIEW anomaly_summary AS
SELECT 
    DATE(d.detected_at) as detection_date,
    COUNT(*) as total_detections,
    SUM(CASE WHEN d.is_anomaly THEN 1 ELSE 0 END) as anomaly_count,
    AVG(d.confidence_score) as avg_confidence,
    COUNT(r.id) as reviewed_count,
    SUM(CASE WHEN r.human_verdict = 'true_positive' THEN 1 ELSE 0 END) as true_positives
FROM detections d
LEFT JOIN reviews r ON d.id = r.detection_id
GROUP BY DATE(d.detected_at)
ORDER BY detection_date DESC;

CREATE VIEW user_activity AS
SELECT 
    u.id,
    u.username,
    u.email,
    u.role,
    COUNT(i.id) as images_uploaded,
    COUNT(r.id) as reviews_completed,
    u.last_login
FROM users u
LEFT JOIN images i ON u.id = i.uploaded_by
LEFT JOIN reviews r ON u.id = r.reviewer_id
GROUP BY u.id, u.username, u.email, u.role, u.last_login;

-- Insert default admin user (password: admin123)
INSERT INTO users (username, email, password_hash, first_name, last_name, role) VALUES
('admin', 'admin@wwtp.local', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewUagjTqgjKJnJZO', 'System', 'Administrator', 'admin');

-- Insert sample data for development (optional)
INSERT INTO users (username, email, password_hash, first_name, last_name, role) VALUES
('reviewer1', 'reviewer1@wwtp.local', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewUagjTqgjKJnJZO', 'John', 'Reviewer', 'reviewer'),
('operator1', 'operator1@wwtp.local', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewUagjTqgjKJnJZO', 'Jane', 'Operator', 'operator');

-- Grant permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO wwtp_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO wwtp_user;