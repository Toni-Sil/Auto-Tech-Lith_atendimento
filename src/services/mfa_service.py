import pyotp
import qrcode
import base64
import io
from typing import Tuple

class MFAService:
    @staticmethod
    def generate_secret() -> str:
        """Generate a new random base32 MFA secret."""
        return pyotp.random_base32()
        
    @staticmethod
    def get_provisioning_uri(secret: str, username: str, issuer_name: str = "AutoTechLith") -> str:
        """Generate a provisioning URI for authenticator apps."""
        return pyotp.totp.TOTP(secret).provisioning_uri(name=username, issuer_name=issuer_name)
        
    @staticmethod
    def generate_qr_code_base64(uri: str) -> str:
        """Generate a base64 encoded QR code PNG for the provisioning URI."""
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(uri)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        return base64.b64encode(buffered.getvalue()).decode()
        
    @staticmethod
    def verify_totp(secret: str, code: str) -> bool:
        """Verify the TOTP code against the given secret."""
        if not secret or not code:
            return False
        totp = pyotp.TOTP(secret)
        return totp.verify(code, valid_window=1) # Validate current + 1 past/future window (30s)

mfa_service = MFAService()
