
from sqlalchemy import Column, Integer, BigInteger, String, Boolean, DateTime, Text, func, ForeignKey
from sqlalchemy.orm import relationship
from src.models.database import Base

class AdminUser(Base):
    __tablename__ = "admin_users"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True)
    username = Column(String, unique=True, index=True, nullable=True) # Nullable for migration compatibility
    password_hash = Column(String, nullable=True)
    
    telegram_id = Column(BigInteger, unique=True, index=True, nullable=True) # Nullable until linked
    name = Column(String, nullable=False)
    role = Column(String, default="admin") # Legacy string role (owner, admin, operator)
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=True) # Dynamic RBAC role
    access_code = Column(String, nullable=True) # Standard login should be preferred
    is_trusted = Column(Boolean, default=False)
    notes = Column(Text, nullable=True) # JSON or encrypted text
    
    # Profile Extensions
    email = Column(String, unique=True, index=True, nullable=True)
    email_verified = Column(Boolean, default=False) # NEW
    phone = Column(String, nullable=True)
    phone_verified = Column(Boolean, default=False) # NEW
    phone_otp = Column(String, nullable=True) # NEW for OTP
    telegram_username = Column(String, nullable=True)
    avatar_url = Column(String, nullable=True)
    bio = Column(Text, nullable=True)
    company_role = Column(String, nullable=True)
    notification_preference = Column(String, default="email") # email, telegram, whatsapp
    
    # Security & Brute Force Protection
    failed_login_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime(timezone=True), nullable=True)
    mfa_enabled = Column(Boolean, default=False)
    mfa_secret = Column(String, nullable=True) # Encrypted TOTP secret
    
    # Account Recovery
    recovery_token = Column(String, nullable=True) # Hashed token
    recovery_token_expires_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_active_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    tenant = relationship("Tenant", back_populates="admins")
    custom_role = relationship("Role", back_populates="users")

    def __repr__(self):
        return f"<AdminUser(name={self.name}, role={self.role})>"
