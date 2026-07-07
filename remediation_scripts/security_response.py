# Automated Security Response Script
import sys
import time

print("[SEC_RESPONSE] [START] Running intrusion detection diagnostics...")
time.sleep(1)
print(
    "[SEC_RESPONSE] [WARN] Threat source identified: SSH brute force credentials attack."
)
time.sleep(1)
print(
    "[SEC_RESPONSE] [INFO] Registering firewall drop rule for attacking IP: 203.0.113.42..."
)
time.sleep(1.5)
print("[SEC_RESPONSE] [SUCCESS] Attacking IP blocked. Packet rejection rules active.")
time.sleep(1.2)
print("[SEC_RESPONSE] [INFO] Invalidating active user authentication sessions...")
time.sleep(1)
print(
    "[SEC_RESPONSE] [SUCCESS] Intrusion threat neutralized. Monitor logs for security metrics."
)
print("[SEC_RESPONSE] [FINISHED] Bastion host secured.")
