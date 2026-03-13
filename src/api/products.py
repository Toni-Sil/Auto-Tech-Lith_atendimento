import csv
import io
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.middleware.auth import require_auth
from src.models.database import get_db  # ✅ FIXED: was get_session
from src.models.product import Product
from src.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter(prefix="/api/products", tags=["products"])


class ProductCreate(BaseModel):
    name: str
    description: Optional[str] = None
    short_description: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[str] = None
    price: float
    currency: str = "BRL"
    is_recurring: bool = False
    billing_cycle: Optional[str] = None
    stock_quantity: int = 0
    unlimited_stock: bool = True
    is_active: bool = True
    is_featured: bool = False


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    short_description: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[str] = None
    price: Optional[float] = None
    currency: Optional[str] = None
    is_recurring: Optional[bool] = None
    billing_cycle: Optional[str] = None
    stock_quantity: Optional[int] = None
    unlimited_stock: Optional[bool] = None
    is_active: Optional[bool] = None
    is_featured: Optional[bool] = None


@router.get("/")
async def list_products(
    session: AsyncSession = Depends(get_db),  # ✅ FIXED
    user=Depends(require_auth),
    category: Optional[str] = None,
    search: Optional[str] = None,
    active_only: bool = True,
    skip: int = 0,
    limit: int = 50,
):
    """List products with optional filters."""
    try:
        stmt = select(Product)

        # Filter by tenant (master admin sees all, tenants see theirs + global)
        if user.get("is_master_admin"):
            pass  # See everything
        else:
            tenant_id = user.get("tenant_id")
            stmt = stmt.where(
                or_(Product.tenant_id == tenant_id, Product.tenant_id == None)
            )

        # Category filter
        if category:
            stmt = stmt.where(Product.category == category)

        # Search filter
        if search:
            search_term = f"%{search}%"
            stmt = stmt.where(
                or_(
                    Product.name.ilike(search_term),
                    Product.description.ilike(search_term),
                )
            )

        # Active filter
        if active_only:
            stmt = stmt.where(Product.is_active == True)

        stmt = stmt.offset(skip).limit(limit)
        result = await session.execute(stmt)
        products = result.scalars().all()

        return {
            "products": [
                {
                    "id": p.id,
                    "name": p.name,
                    "description": p.description,
                    "short_description": p.short_description,
                    "category": p.category,
                    "tags": p.tags,
                    "price": float(p.price),
                    "currency": p.currency,
                    "is_recurring": p.is_recurring,
                    "billing_cycle": p.billing_cycle,
                    "stock_quantity": p.stock_quantity,
                    "unlimited_stock": p.unlimited_stock,
                    "is_active": p.is_active,
                    "is_featured": p.is_featured,
                    "created_at": p.created_at.isoformat() if p.created_at else None,
                }
                for p in products
            ],
            "total": len(products),
        }
    except Exception as e:
        logger.error(f"Error listing products: {e}")
        raise HTTPException(status_code=500, detail="Failed to list products")


@router.get("/categories")
async def list_categories(
    session: AsyncSession = Depends(get_db), user=Depends(require_auth)  # ✅ FIXED
):
    """Get list of all product categories."""
    try:
        stmt = select(Product.category.distinct()).where(
            Product.category != None, Product.is_active == True
        )

        if not user.get("is_master_admin"):
            tenant_id = user.get("tenant_id")
            stmt = stmt.where(
                or_(Product.tenant_id == tenant_id, Product.tenant_id == None)
            )

        result = await session.execute(stmt)
        categories = [row[0] for row in result.all() if row[0]]

        return {"categories": sorted(categories)}
    except Exception as e:
        logger.error(f"Error listing categories: {e}")
        raise HTTPException(status_code=500, detail="Failed to list categories")


@router.get("/{product_id}")
async def get_product(
    product_id: int,
    session: AsyncSession = Depends(get_db),  # ✅ FIXED
    user=Depends(require_auth),
):
    """Get a specific product by ID."""
    try:
        stmt = select(Product).where(Product.id == product_id)

        if not user.get("is_master_admin"):
            tenant_id = user.get("tenant_id")
            stmt = stmt.where(
                or_(Product.tenant_id == tenant_id, Product.tenant_id == None)
            )

        result = await session.execute(stmt)
        product = result.scalar_one_or_none()

        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

        return {
            "id": product.id,
            "name": product.name,
            "description": product.description,
            "short_description": product.short_description,
            "category": product.category,
            "tags": product.tags,
            "price": float(product.price),
            "currency": product.currency,
            "is_recurring": product.is_recurring,
            "billing_cycle": product.billing_cycle,
            "stock_quantity": product.stock_quantity,
            "unlimited_stock": product.unlimited_stock,
            "is_active": product.is_active,
            "is_featured": product.is_featured,
            "specifications": product.specifications,
            "images": product.images,
            "created_at": (
                product.created_at.isoformat() if product.created_at else None
            ),
            "updated_at": (
                product.updated_at.isoformat() if product.updated_at else None
            ),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting product: {e}")
        raise HTTPException(status_code=500, detail="Failed to get product")


@router.post("/")
async def create_product(
    product: ProductCreate,
    session: AsyncSession = Depends(get_db),  # ✅ FIXED
    user=Depends(require_auth),
):
    """Create a new product."""
    try:
        # Only master admin or tenant admins can create products
        tenant_id = None if user.get("is_master_admin") else user.get("tenant_id")

        new_product = Product(
            tenant_id=tenant_id,
            name=product.name,
            description=product.description,
            short_description=product.short_description,
            category=product.category,
            tags=product.tags,
            price=product.price,
            currency=product.currency,
            is_recurring=product.is_recurring,
            billing_cycle=product.billing_cycle,
            stock_quantity=product.stock_quantity,
            unlimited_stock=product.unlimited_stock,
            is_active=product.is_active,
            is_featured=product.is_featured,
        )

        session.add(new_product)
        await session.commit()
        await session.refresh(new_product)

        logger.info(f"Product created: {new_product.id} - {new_product.name}")

        return {"id": new_product.id, "message": "Product created successfully"}
    except Exception as e:
        logger.error(f"Error creating product: {e}")
        raise HTTPException(status_code=500, detail="Failed to create product")


@router.put("/{product_id}")
async def update_product(
    product_id: int,
    product: ProductUpdate,
    session: AsyncSession = Depends(get_db),  # ✅ FIXED
    user=Depends(require_auth),
):
    """Update an existing product."""
    try:
        stmt = select(Product).where(Product.id == product_id)

        if not user.get("is_master_admin"):
            tenant_id = user.get("tenant_id")
            stmt = stmt.where(Product.tenant_id == tenant_id)

        result = await session.execute(stmt)
        db_product = result.scalar_one_or_none()

        if not db_product:
            raise HTTPException(status_code=404, detail="Product not found")

        # Update fields
        update_data = product.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_product, field, value)

        await session.commit()

        logger.info(f"Product updated: {product_id}")

        return {"message": "Product updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating product: {e}")
        raise HTTPException(status_code=500, detail="Failed to update product")


@router.delete("/{product_id}")
async def delete_product(
    product_id: int,
    session: AsyncSession = Depends(get_db),  # ✅ FIXED
    user=Depends(require_auth),
):
    """Delete a product (soft delete by setting is_active=False)."""
    try:
        stmt = select(Product).where(Product.id == product_id)

        if not user.get("is_master_admin"):
            tenant_id = user.get("tenant_id")
            stmt = stmt.where(Product.tenant_id == tenant_id)

        result = await session.execute(stmt)
        product = result.scalar_one_or_none()

        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

        # Soft delete
        product.is_active = False
        await session.commit()

        logger.info(f"Product deleted (soft): {product_id}")

        return {"message": "Product deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting product: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete product")


@router.post("/import")
async def import_products_csv(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db),  # ✅ FIXED
    user=Depends(require_auth),
):
    """Import products from CSV file.

    CSV format: name,description,category,price,currency,is_recurring
    """
    try:
        if not file.filename.endswith(".csv"):
            raise HTTPException(status_code=400, detail="Only CSV files are supported")

        tenant_id = None if user.get("is_master_admin") else user.get("tenant_id")

        content = await file.read()
        csv_file = io.StringIO(content.decode("utf-8"))
        reader = csv.DictReader(csv_file)

        imported = 0
        errors = []

        for row_num, row in enumerate(reader, start=2):
            try:
                product = Product(
                    tenant_id=tenant_id,
                    name=row["name"],
                    description=row.get("description"),
                    category=row.get("category"),
                    price=float(row["price"]),
                    currency=row.get("currency", "BRL"),
                    is_recurring=row.get("is_recurring", "false").lower() == "true",
                    is_active=True,
                )
                session.add(product)
                imported += 1
            except Exception as e:
                errors.append(f"Row {row_num}: {str(e)}")

        await session.commit()

        logger.info(f"Products imported: {imported} successful, {len(errors)} errors")

        return {"imported": imported, "errors": errors[:10]}  # Return first 10 errors
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error importing products: {e}")
        raise HTTPException(status_code=500, detail="Failed to import products")
