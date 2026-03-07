"""
Product Model - Service/Product Catalog

Supports the catalog service with product information,
pricing, categories, and stock management.
"""

from sqlalchemy import Column, Integer, String, Text, Numeric, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from src.models.database import Base


class Product(Base):
    __tablename__ = "products"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)
    
    # Basic Info
    name = Column(String(200), nullable=False, index=True)
    description = Column(Text, nullable=True)
    short_description = Column(String(500), nullable=True)
    
    # Categorization
    category = Column(String(100), nullable=True, index=True)
    tags = Column(Text, nullable=True)  # Comma-separated
    
    # Pricing
    price = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(3), default="BRL")
    is_recurring = Column(Boolean, default=False)  # Monthly subscription?
    billing_cycle = Column(String(20), nullable=True)  # monthly, yearly, one-time
    
    # Stock (optional, for physical products)
    stock_quantity = Column(Integer, default=0)
    unlimited_stock = Column(Boolean, default=True)
    
    # Visibility
    is_active = Column(Boolean, default=True, index=True)
    is_featured = Column(Boolean, default=False)
    
    # Additional data
    specifications = Column(JSON, nullable=True)  # Technical specs
    images = Column(JSON, nullable=True)  # Array of image URLs
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    tenant = relationship("Tenant", back_populates="products")
    
    def __repr__(self):
        return f"<Product(id={self.id}, name='{self.name}', price={self.price})>"
