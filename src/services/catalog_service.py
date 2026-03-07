"""
Catalog Service - Product and Service Management

Provides product/service catalog functionality for customer queries,
including search, filtering, pricing, and recommendations.
"""

from typing import List, Optional, Dict, Any
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.database import async_session
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class CatalogService:
    """
    Manages product/service catalog with search and recommendation capabilities.
    """
    
    async def search_products(
        self,
        query: str,
        tenant_id: Optional[int] = None,
        category: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Search products/services with filters.
        
        Args:
            query: Search term (name, description, tags)
            tenant_id: Filter by tenant (None for master catalog)
            category: Filter by category
            min_price/max_price: Price range filter
            limit: Max results
            
        Returns:
            List of product dicts
        """
        async with async_session() as session:
            try:
                # Import Product model dynamically to avoid circular imports
                from src.models.product import Product
                
                stmt = select(Product).where(Product.is_active == True)
                
                # Tenant filter
                if tenant_id is not None:
                    stmt = stmt.where(
                        or_(Product.tenant_id == tenant_id, Product.tenant_id == None)
                    )
                
                # Search query
                if query:
                    search_term = f"%{query.lower()}%"
                    stmt = stmt.where(
                        or_(
                            Product.name.ilike(search_term),
                            Product.description.ilike(search_term),
                            Product.tags.ilike(search_term)
                        )
                    )
                
                # Category filter
                if category:
                    stmt = stmt.where(Product.category == category)
                
                # Price range
                if min_price is not None:
                    stmt = stmt.where(Product.price >= min_price)
                if max_price is not None:
                    stmt = stmt.where(Product.price <= max_price)
                
                stmt = stmt.limit(limit)
                
                result = await session.execute(stmt)
                products = result.scalars().all()
                
                return [
                    {
                        "id": p.id,
                        "name": p.name,
                        "description": p.description,
                        "category": p.category,
                        "price": float(p.price),
                        "currency": p.currency or "BRL",
                        "available": p.stock_quantity > 0 if hasattr(p, 'stock_quantity') else True,
                        "tags": p.tags.split(",") if p.tags else []
                    }
                    for p in products
                ]
                
            except ImportError:
                logger.warning("Product model not found, returning empty catalog")
                return []
            except Exception as e:
                logger.error(f"Catalog search error: {e}", exc_info=True)
                return []
    
    async def get_product_by_id(
        self,
        product_id: int,
        tenant_id: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get detailed product information by ID.
        """
        async with async_session() as session:
            try:
                from src.models.product import Product
                
                stmt = select(Product).where(
                    Product.id == product_id,
                    Product.is_active == True
                )
                
                if tenant_id is not None:
                    stmt = stmt.where(
                        or_(Product.tenant_id == tenant_id, Product.tenant_id == None)
                    )
                
                result = await session.execute(stmt)
                product = result.scalar_one_or_none()
                
                if not product:
                    return None
                
                return {
                    "id": product.id,
                    "name": product.name,
                    "description": product.description,
                    "category": product.category,
                    "price": float(product.price),
                    "currency": product.currency or "BRL",
                    "available": product.stock_quantity > 0 if hasattr(product, 'stock_quantity') else True,
                    "stock": product.stock_quantity if hasattr(product, 'stock_quantity') else None,
                    "tags": product.tags.split(",") if product.tags else [],
                    "specifications": product.specifications if hasattr(product, 'specifications') else {},
                    "images": product.images if hasattr(product, 'images') else []
                }
                
            except ImportError:
                return None
            except Exception as e:
                logger.error(f"Get product error: {e}")
                return None
    
    async def get_categories(self, tenant_id: Optional[int] = None) -> List[str]:
        """
        Get list of available product categories.
        """
        async with async_session() as session:
            try:
                from src.models.product import Product
                
                stmt = select(Product.category.distinct()).where(
                    Product.is_active == True,
                    Product.category != None
                )
                
                if tenant_id is not None:
                    stmt = stmt.where(
                        or_(Product.tenant_id == tenant_id, Product.tenant_id == None)
                    )
                
                result = await session.execute(stmt)
                categories = [row[0] for row in result.all() if row[0]]
                
                return sorted(categories)
                
            except ImportError:
                return []
            except Exception as e:
                logger.error(f"Get categories error: {e}")
                return []
    
    async def recommend_products(
        self,
        customer_id: int,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Get product recommendations based on customer history.
        
        Simple algorithm: most viewed/purchased categories.
        """
        # TODO: Implement recommendation logic based on:
        # - Customer purchase history
        # - Conversation topics
        # - Similar customer preferences
        
        # For now, return popular products
        return await self.search_products(
            query="",
            limit=limit
        )


# Singleton
catalog_service = CatalogService()
