# WWTP Anomaly Detection System

A production-ready microservices architecture for detecting anomalies in water treatment plant images using computer vision and machine learning.

## Architecture Overview

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   React Frontend │    │  Nginx Proxy    │    │  Auth Service   │
│                 │    │                 │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                ▲
                                │
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ Upload Service  │    │ Review Service  │    │   ML Worker     │
│                 │    │                 │    │  (ResNet CNN)   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                ▲
                                │
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   PostgreSQL    │    │    RabbitMQ     │    │     Redis       │
│                 │    │   (Queue)       │    │   (Cache)       │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                ▲
                                │
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│    MinIO        │    │   Prometheus    │    │    Grafana      │
│ (Object Storage)│    │  (Metrics)      │    │  (Monitoring)   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## Features

- **Microservices Architecture**: Scalable, maintainable service separation
- **Computer Vision**: ResNet-based CNN for anomaly detection in WWTP images
- **Real-time Processing**: Queue-based async processing with RabbitMQ
- **User Management**: JWT-based authentication and role-based access
- **Review Workflow**: Human-in-the-loop validation for ML predictions
- **Monitoring**: Comprehensive metrics with Prometheus and Grafana
- **Storage**: Distributed object storage with MinIO
- **Production Ready**: Docker containerization with proper logging and error handling

## Quick Start

1. **Clone the repository**:
   ```bash
   git clone https://github.com/Homaei/Anomalyinwater.git
   cd Anomalyinwater
   ```

2. **Set up environment**:
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

3. **Start services**:
   ```bash
   docker-compose up -d
   ```

4. **Access the application**:
   - Frontend: http://localhost:3000
   - API Gateway: http://localhost:80
   - Grafana: http://localhost:3001 (admin/admin123)
   - RabbitMQ Management: http://localhost:15672 (admin/admin123)

## Services

### Frontend (React)
- **Port**: 3000
- **Features**: Image upload, anomaly review dashboard, real-time notifications
- **Tech Stack**: React, TypeScript, Material-UI, WebSocket

### Auth Service
- **Port**: 8001
- **Features**: User registration, JWT authentication, role management
- **Tech Stack**: FastAPI, SQLAlchemy, bcrypt, Redis

### Upload Service
- **Port**: 8002
- **Features**: Image upload, preprocessing, metadata extraction
- **Tech Stack**: FastAPI, Pillow, MinIO, RabbitMQ

### Review Service
- **Port**: 8003
- **Features**: Anomaly review workflow, feedback collection
- **Tech Stack**: FastAPI, SQLAlchemy, WebSocket

### ML Worker
- **Features**: ResNet-based anomaly detection, model inference
- **Tech Stack**: Python, PyTorch, torchvision, OpenCV

## Database Schema

- **Users**: Authentication and user management
- **Images**: Image metadata and storage references
- **Detections**: ML model predictions and confidence scores
- **Reviews**: Human validation of anomaly detections
- **Audit Logs**: System activity tracking

## Development

### Prerequisites
- Docker & Docker Compose
- Python 3.9+
- Node.js 18+
- CUDA (optional, for GPU acceleration)

### Local Development
```bash
# Backend development
cd backend/auth-service
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8001

# Frontend development
cd frontend
npm install
npm start

# Run tests
pytest tests/
npm test
```

### Testing
```bash
# Run all tests
make test

# Run specific test suites
pytest tests/backend/
npm test -- --coverage
docker-compose -f docker-compose.test.yml up
```

## Deployment

### Production Deployment
```bash
# Set production environment
export ENVIRONMENT=production

# Deploy with Docker Swarm
docker stack deploy -c docker-compose.prod.yml wwtp

# Or deploy with Kubernetes
kubectl apply -f k8s/
```

### Environment Variables
See `.env.example` for all configuration options.

## Monitoring & Observability

- **Metrics**: Prometheus collects metrics from all services
- **Dashboards**: Grafana provides visualization and alerting
- **Logs**: Centralized logging with structured JSON format
- **Health Checks**: Service health endpoints for monitoring

## API Documentation

- Auth Service: http://localhost:8001/docs
- Upload Service: http://localhost:8002/docs
- Review Service: http://localhost:8003/docs

## Security

- JWT-based authentication
- Role-based access control
- Input validation and sanitization
- Secure file upload handling
- Rate limiting and CORS protection

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

For issues and questions, please create an issue in the GitHub repository.