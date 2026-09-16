# Synthetic Statutory Records

This folder stores seed fixtures and definitions for synthetic statutory registry databases:
- GSTN Active/Cancelled records
- Udyam MSME Classifications (Micro, Small, Medium)
- DPIIT Recognition numbers
- EPFO Establishment profiles
- ESIC Employer codes
- NSIC / SPRS registrations
- DigiLocker document hashes & issuer keys
- Debarment / Blacklist orders with effective date intervals

All records are programmatically generated using `scripts/seed_mock_data.py` and `backend/app/services/mock_seeder.py`.
