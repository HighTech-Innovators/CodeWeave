# Constraints

**Constraint:** Use PyTorch with CPU only.

**Constraint:** Do not perform any GIT commits. These will be handled externally.

**Constraint:** Use codecarbon for energy measurement in integration tests (`pip install codecarbon`; wrap benchmark runs with `EmissionsTracker`).