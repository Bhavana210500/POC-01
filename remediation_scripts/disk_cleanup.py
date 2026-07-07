# Automated Disk Cleanup Script
import sys
import time
import random

print("[DISK_CLEANUP] [START] Analyzing filesystem partitions...")
time.sleep(1)
print(
    "[DISK_CLEANUP] [INFO] Partition /data space consumption: 94%. Critical threshold exceeded."
)
time.sleep(1.5)
print(
    "[DISK_CLEANUP] [INFO] Commencing compression of old log archives in /var/log/db/archive..."
)
time.sleep(1.2)
print("[DISK_CLEANUP] [SUCCESS] Compressed 84 log files. Gained 14.3GB disk storage.")
time.sleep(1)
print("[DISK_CLEANUP] [INFO] Clearing stale caches in /tmp directory...")
time.sleep(1)
print("[DISK_CLEANUP] [SUCCESS] Deleted 254 temp caches. Gained 2.8GB disk storage.")
time.sleep(1)
print("[DISK_CLEANUP] [SUCCESS] Overall partition space reduced to 67%.")
print("[DISK_CLEANUP] [FINISHED] Disk space within bounds.")
