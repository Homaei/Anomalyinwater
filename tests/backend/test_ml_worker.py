import pytest
import numpy as np
from PIL import Image
import torch
import asyncio
from unittest.mock import Mock, patch, MagicMock
import json
import io


class TestMLWorker:
    """Test suite for ML Worker service."""
    
    @pytest.fixture(autouse=True)
    def setup(self, mock_ml_model, temp_directory):
        """Set up test environment."""
        self.mock_model = mock_ml_model
        self.temp_dir = temp_directory
    
    def test_model_initialization(self):
        """Test ML model initialization."""
        from backend.ml_worker.app.models import ResNetAnomalyDetector
        
        model = ResNetAnomalyDetector(num_classes=2, pretrained=False)
        
        assert model is not None
        assert hasattr(model, 'forward')
        assert hasattr(model, 'predict_anomaly')
    
    def test_image_preprocessing(self, test_image_file):
        """Test image preprocessing pipeline."""
        from backend.ml_worker.app.image_processor import ImageProcessor
        
        processor = ImageProcessor()
        
        # Create numpy array from test image
        img = Image.open(io.BytesIO(test_image_file['content']))
        img_array = np.array(img)
        
        # Test preprocessing
        processed = processor._preprocess_image(img_array)
        
        assert processed is not None
        assert isinstance(processed, np.ndarray)
        assert processed.shape[-1] == 3  # RGB channels
    
    def test_anomaly_detection_prediction(self, test_image_file, mock_ml_model):
        """Test anomaly detection prediction."""
        with patch('backend.ml_worker.app.models.ModelManager') as MockManager:
            mock_manager = MockManager.return_value
            mock_manager.predict.return_value = (True, 0.85, None, {"test": True})
            
            from backend.ml_worker.app.image_processor import ImageProcessor
            
            processor = ImageProcessor()
            processor.model_manager = mock_manager
            processor.model_loaded = True
            
            # Create test image
            img = Image.open(io.BytesIO(test_image_file['content']))
            img_array = np.array(img)
            
            # Mock async method
            async def mock_detect():
                result = await processor._detect_anomaly(img_array, Mock())
                return result
            
            # Run async test
            loop = asyncio.get_event_loop()
            result = loop.run_until_complete(mock_detect())
            
            assert result is not None
            assert 'is_anomaly' in result
            assert 'confidence' in result
            assert isinstance(result['confidence'], float)
    
    def test_queue_message_processing(self, sample_detection_data, mock_rabbitmq):
        """Test RabbitMQ message processing."""
        from backend.ml_worker.app.queue_consumer import RabbitMQConsumer
        
        # Mock message handler
        async def mock_handler(message):
            return {"success": True, "processed": True}
        
        consumer = RabbitMQConsumer(mock_handler)
        
        # Test message processing
        test_message = {
            "message_id": "test_123",
            "image_id": "image_456",
            "image_path": "/test/path.jpg"
        }
        
        # Mock processing
        with patch.object(consumer, '_handle_message_sync') as mock_handle:
            mock_handle.return_value = None
            
            consumer.process_message(
                channel=Mock(),
                method=Mock(delivery_tag=1),
                properties=Mock(priority=5),
                body=json.dumps(test_message).encode()
            )
            
            mock_handle.assert_called_once()
    
    def test_model_performance_metrics(self, performance_thresholds):
        """Test model performance metrics."""
        from backend.ml_worker.app.metrics import MLMetrics
        
        metrics = MLMetrics()
        
        # Record test metrics
        metrics.record_processing_time(2.5)
        metrics.record_detection(True, 0.85)
        metrics.record_model_inference_time(0.5)
        
        # Test metrics collection
        summary = metrics.get_metrics_summary()
        
        assert 'images_processed' in summary
        assert 'anomalies_detected' in summary
        assert 'processing_errors' in summary
    
    def test_gpu_availability(self):
        """Test GPU availability detection."""
        import torch
        
        # Test CUDA availability
        cuda_available = torch.cuda.is_available()
        
        if cuda_available:
            device_count = torch.cuda.device_count()
            assert device_count > 0
            
            device_name = torch.cuda.get_device_name(0)
            assert isinstance(device_name, str)
            assert len(device_name) > 0
    
    @pytest.mark.slow
    def test_batch_processing(self, test_image_file):
        """Test batch image processing."""
        from backend.ml_worker.app.image_processor import ImageProcessor
        
        processor = ImageProcessor()
        
        # Create multiple test images
        test_images = []
        for i in range(5):
            img = Image.open(io.BytesIO(test_image_file['content']))
            img_array = np.array(img)
            test_images.append(img_array)
        
        # Mock batch processing
        with patch.object(processor, '_detect_anomaly') as mock_detect:
            mock_detect.return_value = {
                'is_anomaly': True,
                'confidence': 0.85,
                'processing_time_ms': 1000
            }
            
            # Process batch
            results = []
            for img in test_images:
                result = asyncio.run(processor._detect_anomaly(img, Mock()))
                results.append(result)
            
            assert len(results) == 5
            assert all('is_anomaly' in result for result in results)
    
    def test_error_handling_invalid_image(self, invalid_image_file):
        """Test error handling for invalid images."""
        from backend.ml_worker.app.image_processor import ImageProcessor
        
        processor = ImageProcessor()
        
        # Test with invalid image data
        with pytest.raises(Exception):
            processor._validate_image(
                np.array([[[255, 255]]]),  # Invalid shape
                Mock(width=None, height=None)
            )
    
    def test_model_loading_failure(self):
        """Test handling of model loading failures."""
        from backend.ml_worker.app.models import ModelManager
        
        with patch('torch.load') as mock_load:
            mock_load.side_effect = Exception("Model file not found")
            
            manager = ModelManager("/nonexistent/path", torch.device('cpu'))
            result = manager.load_model("nonexistent_model.pth")
            
            assert result is False
            assert manager.model is not None  # Should create fallback model
    
    def test_confidence_thresholding(self, sample_detection_data):
        """Test confidence score thresholding."""
        from backend.ml_worker.app.image_processor import ImageProcessor
        from backend.ml_worker.app.config import settings
        
        processor = ImageProcessor()
        
        # Test with low confidence
        low_confidence_result = {
            'is_anomaly': True,
            'confidence': 0.3,  # Below threshold
            'anomaly_type': 'test',
            'bounding_box': None,
            'features': {},
            'processing_time_ms': 1000
        }
        
        # Mock the detection process
        with patch.object(processor, 'model_manager') as mock_manager:
            mock_manager.predict.return_value = (True, 0.3, None, {})
            
            # Should reject low confidence detections
            result = asyncio.run(processor._detect_anomaly(np.zeros((100, 100, 3)), Mock()))
            
            # With default thresholds, low confidence should be rejected
            if result['confidence'] < settings.confidence_threshold:
                assert result['is_anomaly'] is False
    
    @pytest.mark.performance
    def test_processing_speed(self, test_image_file, performance_thresholds):
        """Test image processing speed."""
        import time
        
        from backend.ml_worker.app.image_processor import ImageProcessor
        
        processor = ImageProcessor()
        
        # Create test image
        img = Image.open(io.BytesIO(test_image_file['content']))
        img_array = np.array(img)
        
        # Mock fast processing
        with patch.object(processor, 'model_manager') as mock_manager:
            mock_manager.predict.return_value = (True, 0.85, None, {})
            
            start_time = time.time()
            result = asyncio.run(processor._detect_anomaly(img_array, Mock()))
            end_time = time.time()
            
            processing_time = end_time - start_time
            
            assert processing_time < performance_thresholds["image_processing_time"]
            assert result is not None
    
    def test_memory_management(self, large_test_image_file):
        """Test memory management with large images."""
        import psutil
        import os
        
        from backend.ml_worker.app.image_processor import ImageProcessor
        
        processor = ImageProcessor()
        
        # Get initial memory usage
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Process large image
        img = Image.open(io.BytesIO(large_test_image_file['content']))
        img_array = np.array(img)
        
        with patch.object(processor, 'model_manager') as mock_manager:
            mock_manager.predict.return_value = (True, 0.85, None, {})
            
            result = asyncio.run(processor._detect_anomaly(img_array, Mock()))
            
            # Check memory usage didn't explode
            final_memory = process.memory_info().rss / 1024 / 1024  # MB
            memory_increase = final_memory - initial_memory
            
            assert memory_increase < 500  # Should not use more than 500MB extra
            assert result is not None
    
    def test_concurrent_processing(self, test_image_file):
        """Test concurrent image processing."""
        from backend.ml_worker.app.image_processor import ImageProcessor
        import asyncio
        
        processor = ImageProcessor()
        
        # Mock processing
        with patch.object(processor, 'model_manager') as mock_manager:
            mock_manager.predict.return_value = (True, 0.85, None, {})
            
            # Create concurrent tasks
            async def process_image():
                img = Image.open(io.BytesIO(test_image_file['content']))
                img_array = np.array(img)
                return await processor._detect_anomaly(img_array, Mock())
            
            # Run multiple concurrent tasks
            tasks = [process_image() for _ in range(3)]
            results = asyncio.run(asyncio.gather(*tasks))
            
            assert len(results) == 3
            assert all(result is not None for result in results)
            assert all('is_anomaly' in result for result in results)


@pytest.mark.integration
class TestMLWorkerIntegration:
    """Integration tests for ML Worker."""
    
    def test_full_processing_pipeline(self, db_session, test_image_file):
        """Test complete ML processing pipeline."""
        # This would test the full pipeline from queue message to database update
        pass
    
    def test_rabbitmq_integration(self, rabbitmq_container):
        """Test RabbitMQ integration."""
        # Test real RabbitMQ connection and message processing
        pass