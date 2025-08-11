import torch
import torch.nn as nn
import torchvision.models as models
from torchvision import transforms
from typing import Tuple, Dict, Any, Optional
import numpy as np
from pathlib import Path
import logging
import time

logger = logging.getLogger(__name__)


class ResNetAnomalyDetector(nn.Module):
    """ResNet-based anomaly detection model for WWTP images"""
    
    def __init__(self, num_classes: int = 2, pretrained: bool = True):
        super(ResNetAnomalyDetector, self).__init__()
        
        # Use ResNet50 as backbone
        self.backbone = models.resnet50(pretrained=pretrained)
        
        # Replace final layer for binary classification (normal/anomaly)
        num_features = self.backbone.fc.in_features
        self.backbone.fc = nn.Sequential(
            nn.Dropout(0.5),
            nn.Linear(num_features, 512),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(512, num_classes)
        )
        
        # Additional features for anomaly localization
        self.feature_extractor = nn.Sequential(
            *list(self.backbone.children())[:-2]  # Remove avgpool and fc
        )
        
        # Global Average Pooling for feature maps
        self.global_avg_pool = nn.AdaptiveAvgPool2d(1)
        
        # Attention mechanism for anomaly localization
        self.attention = nn.Sequential(
            nn.Conv2d(2048, 512, 1),
            nn.ReLU(),
            nn.Conv2d(512, 1, 1),
            nn.Sigmoid()
        )
    
    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Forward pass
        
        Args:
            x: Input tensor (B, C, H, W)
            
        Returns:
            classification_output: Class probabilities (B, num_classes)
            features: Global features (B, 2048)
            attention_map: Attention weights (B, 1, H', W')
        """
        # Extract features
        feature_maps = self.feature_extractor(x)  # (B, 2048, H', W')
        
        # Generate attention map
        attention_map = self.attention(feature_maps)  # (B, 1, H', W')
        
        # Apply attention to features
        attended_features = feature_maps * attention_map
        
        # Global average pooling
        global_features = self.global_avg_pool(attended_features)  # (B, 2048, 1, 1)
        global_features = global_features.view(global_features.size(0), -1)  # (B, 2048)
        
        # Classification
        classification_output = self.backbone.fc(global_features)  # (B, num_classes)
        
        return classification_output, global_features, attention_map
    
    def predict_anomaly(self, x: torch.Tensor) -> Tuple[bool, float, Optional[Dict]]:
        """
        Predict if input contains anomaly
        
        Args:
            x: Input tensor
            
        Returns:
            is_anomaly: Boolean indicating anomaly presence
            confidence: Confidence score (0-1)
            localization: Optional bounding box and attention map
        """
        self.eval()
        with torch.no_grad():
            logits, features, attention_map = self.forward(x)
            probabilities = torch.softmax(logits, dim=1)
            
            # Class 1 is anomaly class
            anomaly_prob = probabilities[0, 1].item()
            is_anomaly = anomaly_prob > 0.5
            
            # Generate localization info if anomaly detected
            localization = None
            if is_anomaly:
                localization = self._generate_localization(attention_map[0], x.shape[-2:])
        
        return is_anomaly, anomaly_prob, localization
    
    def _generate_localization(self, attention_map: torch.Tensor, original_size: Tuple[int, int]) -> Dict:
        """Generate bounding box from attention map"""
        # Resize attention map to original image size
        attention_resized = nn.functional.interpolate(
            attention_map.unsqueeze(0), 
            size=original_size, 
            mode='bilinear', 
            align_corners=False
        )[0, 0]  # (H, W)
        
        # Find connected components above threshold
        attention_np = attention_resized.cpu().numpy()
        threshold = np.percentile(attention_np, 90)  # Top 10% attention
        
        # Find bounding box of high attention region
        high_attention = attention_np > threshold
        if np.any(high_attention):
            rows = np.any(high_attention, axis=1)
            cols = np.any(high_attention, axis=0)
            
            if np.any(rows) and np.any(cols):
                rmin, rmax = np.where(rows)[0][[0, -1]]
                cmin, cmax = np.where(cols)[0][[0, -1]]
                
                return {
                    'x': int(cmin),
                    'y': int(rmin),
                    'width': int(cmax - cmin),
                    'height': int(rmax - rmin),
                    'confidence': float(np.mean(attention_np[rmin:rmax+1, cmin:cmax+1]))
                }
        
        return None


class ModelManager:
    """Manages model loading, saving, and inference"""
    
    def __init__(self, model_path: str, device: torch.device):
        self.model_path = Path(model_path)
        self.device = device
        self.model = None
        self.transform = None
        self._setup_transforms()
    
    def _setup_transforms(self):
        """Setup image preprocessing transforms"""
        self.transform = transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], 
                               std=[0.229, 0.224, 0.225])
        ])
        
        # Augmentation transforms for training
        self.train_transform = transforms.Compose([
            transforms.Resize((256, 256)),
            transforms.RandomCrop(224),
            transforms.RandomHorizontalFlip(0.5),
            transforms.RandomRotation(10),
            transforms.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.2),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], 
                               std=[0.229, 0.224, 0.225])
        ])
    
    def load_model(self, model_name: str) -> bool:
        """Load trained model from disk"""
        try:
            model_file = self.model_path / model_name
            if not model_file.exists():
                logger.warning(f"Model file {model_file} not found, creating new model")
                self.model = ResNetAnomalyDetector()
                self.model.to(self.device)
                return False
            
            # Load model
            checkpoint = torch.load(model_file, map_location=self.device)
            
            self.model = ResNetAnomalyDetector()
            self.model.load_state_dict(checkpoint['model_state_dict'])
            self.model.to(self.device)
            self.model.eval()
            
            logger.info(f"Model loaded successfully from {model_file}")
            logger.info(f"Model version: {checkpoint.get('version', 'unknown')}")
            logger.info(f"Model accuracy: {checkpoint.get('accuracy', 'unknown')}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            # Create new model as fallback
            self.model = ResNetAnomalyDetector()
            self.model.to(self.device)
            return False
    
    def save_model(self, model_name: str, version: str, accuracy: float = None, metadata: Dict = None):
        """Save model to disk"""
        try:
            self.model_path.mkdir(parents=True, exist_ok=True)
            model_file = self.model_path / model_name
            
            checkpoint = {
                'model_state_dict': self.model.state_dict(),
                'version': version,
                'accuracy': accuracy,
                'metadata': metadata or {},
                'timestamp': torch.tensor(time.time())
            }
            
            torch.save(checkpoint, model_file)
            logger.info(f"Model saved to {model_file}")
            
        except Exception as e:
            logger.error(f"Failed to save model: {e}")
            raise
    
    def preprocess_image(self, image: np.ndarray) -> torch.Tensor:
        """Preprocess image for inference"""
        from PIL import Image
        
        # Convert numpy array to PIL Image
        if image.dtype != np.uint8:
            image = (image * 255).astype(np.uint8)
        
        if len(image.shape) == 3 and image.shape[2] == 3:
            pil_image = Image.fromarray(image, 'RGB')
        else:
            pil_image = Image.fromarray(image)
            if pil_image.mode != 'RGB':
                pil_image = pil_image.convert('RGB')
        
        # Apply transforms
        tensor_image = self.transform(pil_image)
        
        # Add batch dimension
        return tensor_image.unsqueeze(0).to(self.device)
    
    def predict(self, image: np.ndarray) -> Tuple[bool, float, Optional[Dict], Dict]:
        """
        Run inference on image
        
        Args:
            image: Input image as numpy array
            
        Returns:
            is_anomaly: Boolean indicating anomaly presence
            confidence: Confidence score
            localization: Bounding box and attention info
            features: Extracted features for analysis
        """
        if self.model is None:
            raise RuntimeError("Model not loaded")
        
        # Preprocess image
        input_tensor = self.preprocess_image(image)
        
        # Run inference
        start_time = time.time()
        is_anomaly, confidence, localization = self.model.predict_anomaly(input_tensor)
        inference_time = (time.time() - start_time) * 1000  # ms
        
        # Extract features for analysis
        with torch.no_grad():
            _, features, attention_map = self.model(input_tensor)
            
        features_dict = {
            'global_features': features[0].cpu().numpy().tolist(),
            'attention_statistics': {
                'mean': float(attention_map.mean()),
                'max': float(attention_map.max()),
                'min': float(attention_map.min()),
                'std': float(attention_map.std())
            },
            'inference_time_ms': inference_time
        }
        
        return is_anomaly, confidence, localization, features_dict
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get model information"""
        if self.model is None:
            return {"status": "not_loaded"}
        
        total_params = sum(p.numel() for p in self.model.parameters())
        trainable_params = sum(p.numel() for p in self.model.parameters() if p.requires_grad)
        
        return {
            "status": "loaded",
            "device": str(self.device),
            "total_parameters": total_params,
            "trainable_parameters": trainable_params,
            "model_size_mb": total_params * 4 / (1024 * 1024),  # Assuming float32
        }