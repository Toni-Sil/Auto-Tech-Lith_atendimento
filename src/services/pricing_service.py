"""
Pricing Service - Dynamic Price Management

Manages product pricing with support for tenant-specific rules,
discounts, and price variations.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional

from sqlalchemy import select

from src.models.database import async_session
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class PricingService:
    """Dynamic pricing engine with tenant support."""

    async def get_price(
        self, product_id: int, tenant_id: Optional[int] = None, quantity: int = 1
    ) -> Dict[str, Any]:
        """
        Get effective price for a product considering tenant rules.

        Returns:
            {
                'base_price': Decimal,
                'final_price': Decimal,
                'discount_pct': float,
                'currency': str
            }
        """
        async with async_session() as session:
            try:
                from src.models.product import Product

                # Get product
                stmt = select(Product).where(Product.id == product_id)
                product = (await session.execute(stmt)).scalar_one_or_none()

                if not product:
                    return {"error": "Product not found"}

                base_price = Decimal(str(product.price))

                # Check for tenant-specific pricing
                if tenant_id:
                    custom_price = await self._get_tenant_price(
                        session, product_id, tenant_id
                    )
                    if custom_price:
                        base_price = custom_price

                # Apply volume discounts
                discount_pct = self._calculate_volume_discount(quantity)
                final_price = base_price * (1 - Decimal(str(discount_pct / 100)))

                return {
                    "base_price": float(base_price),
                    "final_price": float(final_price),
                    "discount_pct": discount_pct,
                    "currency": product.currency or "BRL",
                    "quantity": quantity,
                }

            except Exception as e:
                logger.error(f"Pricing error: {e}")
                return {"error": str(e)}

    async def _get_tenant_price(
        self, session, product_id: int, tenant_id: int
    ) -> Optional[Decimal]:
        """Check for tenant-specific pricing override."""
        try:
            from src.models.config_model import SystemConfig

            # Check if tenant has custom pricing in config
            stmt = select(SystemConfig).where(
                SystemConfig.tenant_id == tenant_id,
                SystemConfig.key == f"product_price_{product_id}",
            )
            config = (await session.execute(stmt)).scalar_one_or_none()

            if config and config.value:
                return Decimal(str(config.value))
        except Exception as e:
            logger.debug(f"No custom pricing for tenant {tenant_id}: {e}")

        return None

    def _calculate_volume_discount(self, quantity: int) -> float:
        """Calculate volume-based discount percentage."""
        if quantity >= 10:
            return 15.0
        elif quantity >= 5:
            return 10.0
        elif quantity >= 3:
            return 5.0
        return 0.0

    async def get_service_pricing(
        self, tenant_id: Optional[int] = None
    ) -> Dict[str, float]:
        """
        Get standard service pricing (installation, maintenance).
        Can be overridden per tenant in SystemConfig.
        """
        defaults = {
            "installation": 2000.00,
            "monthly_maintenance": 300.00,
            "hourly_consulting": 150.00,
            "training_session": 500.00,
        }

        if not tenant_id:
            return defaults

        # Check for tenant overrides
        async with async_session() as session:
            try:
                from src.models.config_model import SystemConfig

                stmt = select(SystemConfig).where(
                    SystemConfig.tenant_id == tenant_id,
                    SystemConfig.key.like("service_price_%"),
                )
                configs = (await session.execute(stmt)).scalars().all()

                for config in configs:
                    service_name = config.key.replace("service_price_", "")
                    if service_name in defaults:
                        defaults[service_name] = float(config.value)
            except Exception as e:
                logger.warning(f"Error loading tenant pricing: {e}")

        return defaults


pricing_service = PricingService()
