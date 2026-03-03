#!/bin/bash
set -e

echo "1. Getting initial token..."
TOKEN=$(curl -s -X POST "http://localhost:8000/api/auth/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=admin123" | jq -r .access_token)

if [ "$TOKEN" == "null" ] || [ -z "$TOKEN" ]; then
    echo "Failed to get token! Response was:"
    curl -s -X POST "http://localhost:8000/api/auth/token" -H "Content-Type: application/x-www-form-urlencoded" -d "username=admin&password=admin123"
    exit 1
fi
echo "Token: $TOKEN"

echo "2. Setting up MFA..."
SECRET=$(curl -s -X POST "http://localhost:8000/api/auth/mfa/setup" \
  -H "Authorization: Bearer $TOKEN" | jq -r .secret)
echo "Secret: $SECRET"

echo "3. Verifying MFA..."
CODE=$(python -c "import pyotp; print(pyotp.TOTP('$SECRET').now())")
curl -s -X POST "http://localhost:8000/api/auth/mfa/verify" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"code\": \"$CODE\"}"

echo -e "\n4. Trying Login without MFA..."
curl -s -X POST "http://localhost:8000/api/auth/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=admin123"

echo -e "\n5. Trying Login WITH MFA..."
CODE=$(python -c "import pyotp; print(pyotp.TOTP('$SECRET').now())")
NEW_TOKEN=$(curl -s -X POST "http://localhost:8000/api/auth/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -H "X-MFA-Token: $CODE" \
  -d "username=admin&password=admin123" | jq -r .access_token)
echo "Login with MFA returned token: $NEW_TOKEN"

echo "6. Disabling MFA..."
CODE=$(python -c "import pyotp; print(pyotp.TOTP('$SECRET').now())")
curl -s -X POST "http://localhost:8000/api/auth/mfa/disable" \
  -H "Authorization: Bearer $NEW_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"code\": \"$CODE\"}"

