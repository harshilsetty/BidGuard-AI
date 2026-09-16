"""
Deterministic Golden Demo Seeder for SIH26100 GeM Procurement Platform.

Guarantees:
- Idempotently creates the Golden Demo Tender (GEM/2026/B/8912450).
- Confirms all 11 benchmark clauses across Technical, Financial, Statutory, Experience, Delivery.
- Ingests and chunks Bidder A (Compliant), Bidder B (Non-Compliant), and Bidder C (Contradictory).
- Runs the Hybrid Compliance Engine producing:
    * Bidder A -> 11 PASS, 0 FAIL, 0 REVIEW (Qualified)
    * Bidder B -> 1 PASS, 10 FAIL, 0 REVIEW (Disqualified - Turnover ₹2.1 Cr < ₹5.0 Cr, 90d > 30d, 32 cores < 64)
    * Bidder C -> 4 PASS, 3 FAIL, 4 REVIEW (Contradiction Detected - 55% vs 32% MII, ₹8.0 Cr vs ₹3.65 Cr)
"""

import asyncio
import os
import sys
import logging
from uuid import UUID
from sqlalchemy import select

# Ensure project backend is on sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core import database
from app.core.database import init_db
from app.models.tender import Tender
from app.models.clause import TenderClause
from app.models.bidder import Bidder
from app.api.v1.bidders import load_demo_bidders
from app.api.v1.evaluations import run_tender_compliance_evaluation, EvaluationRunRequest

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("seed_golden_demo")

BENCHMARK_CLAUSES = [
    {
        "clause_code": "TECH-01",
        "category": "TECHNICAL",
        "title": "Server Compute Infrastructure",
        "description": "Rack servers equipped with minimum 64-core processors and 256GB ECC DDR5 RAM",
        "source_text": "The bidder must provide rack servers equipped with minimum 64-core processors and 256GB ECC DDR5 RAM.",
        "is_mandatory": True,
        "page_number": 1,
        "rule_config": {"type": "NUMERIC_MIN", "parameter": "cpu_cores", "value": 64, "unit": "cores"},
    },
    {
        "clause_code": "TECH-02",
        "category": "TECHNICAL",
        "title": "Hardware Quality & BIS Standards",
        "description": "BIS certification and ISO 9001:2015 quality standards compliance",
        "source_text": "All hardware components must be certified under BIS and comply with ISO 9001:2015 quality standards.",
        "is_mandatory": True,
        "page_number": 1,
        "rule_config": {"type": "DOCUMENT_REQUIRED", "parameter": "bis_and_iso_cert", "value": None},
    },
    {
        "clause_code": "TECH-03",
        "category": "TECHNICAL",
        "title": "OEM Warranty Coverage",
        "description": "3-year comprehensive on-site OEM warranty",
        "source_text": "Comprehensive on-site OEM warranty of 3 years shall be provided for all supplied equipment.",
        "is_mandatory": True,
        "page_number": 1,
        "rule_config": {"type": "NUMERIC_MIN", "parameter": "warranty_years", "value": 3, "unit": "years"},
    },
    {
        "clause_code": "FIN-01",
        "category": "FINANCIAL",
        "title": "Minimum Average Annual Turnover",
        "description": "Average annual turnover of at least INR 5.0 Crores during last 3 financial years",
        "source_text": "Average annual turnover of the bidder during the last three financial years must be at least INR 5.0 Crores.",
        "is_mandatory": True,
        "page_number": 2,
        "rule_config": {"type": "NUMERIC_MIN", "parameter": "average_annual_turnover", "value": 5.0, "unit": "Crores"},
    },
    {
        "clause_code": "FIN-02",
        "category": "FINANCIAL",
        "title": "Audited Balance Sheets Upload",
        "description": "Audited balance sheets and CA certificate with UDIN",
        "source_text": "Audited balance sheets and chartered accountant certificates must be uploaded.",
        "is_mandatory": True,
        "page_number": 2,
        "rule_config": {"type": "DOCUMENT_REQUIRED", "parameter": "audited_balance_sheets", "value": None},
    },
    {
        "clause_code": "FIN-03",
        "category": "FINANCIAL",
        "title": "Earnest Money Deposit (EMD)",
        "description": "Online bank guarantee of INR 10,00,000",
        "source_text": "Bidder must submit an Earnest Money Deposit of INR 10,00,000 via online bank guarantee.",
        "is_mandatory": True,
        "page_number": 2,
        "rule_config": {"type": "NUMERIC_MIN", "parameter": "emd_amount", "value": 1000000, "unit": "INR"},
    },
    {
        "clause_code": "FIN-04",
        "category": "FINANCIAL",
        "title": "EMD Exemption for MSEs",
        "description": "Exemption permissible for registered MSEs",
        "source_text": "EMD exemption is permissible for registered Micro and Small Enterprises (MSEs).",
        "is_mandatory": False,
        "page_number": 2,
        "rule_config": {"type": "CUSTOM", "parameter": "mse_exemption", "value": None},
    },
    {
        "clause_code": "STAT-01",
        "category": "STATUTORY",
        "title": "Make in India (MII) Local Content",
        "description": "Minimum 50 percent local content for Class-I Local Supplier",
        "source_text": "Minimum 50 percent local content is mandatory for qualification under Class-I Local Supplier category.",
        "is_mandatory": True,
        "page_number": 3,
        "rule_config": {"type": "PERCENT_MIN", "parameter": "local_content_percentage", "value": 50, "unit": "%"},
    },
    {
        "clause_code": "STAT-02",
        "category": "STATUTORY",
        "title": "Self-Certification of Local Content",
        "description": "Self-certification indicating percentage of local content",
        "source_text": "Self-certification indicating the percentage of local content must be provided.",
        "is_mandatory": True,
        "page_number": 3,
        "rule_config": {"type": "DOCUMENT_REQUIRED", "parameter": "local_content_self_cert", "value": None},
    },
    {
        "clause_code": "EXP-01",
        "category": "EXPERIENCE",
        "title": "Past Contract Execution",
        "description": "Execution of at least 2 similar enterprise IT contracts in last 3 years",
        "source_text": "Bidder must have successfully executed at least 2 similar enterprise IT contracts in the last 3 years.",
        "is_mandatory": True,
        "page_number": 3,
        "rule_config": {"type": "NUMERIC_MIN", "parameter": "similar_contracts_count", "value": 2, "unit": "contracts"},
    },
    {
        "clause_code": "DEL-01",
        "category": "DELIVERY_SLA",
        "title": "Delivery Schedule & Installation Timeline",
        "description": "Hardware items and software licenses delivered and installed within 30 days",
        "source_text": "All hardware items and software licenses must be delivered and installed within 30 days from contract award.",
        "is_mandatory": True,
        "page_number": 4,
        "rule_config": {"type": "NUMERIC_MAX", "parameter": "delivery_days", "value": 30, "unit": "days"},
    },
]


ADDITIONAL_DEMO_TENDERS = [
    {
        "gem_tender_id": "GEM/2026/B/8912451",
        "title": "Network Security & Firewall Infrastructure Procurement",
        "file_name": "GEM_2026_B_8912451_Network_Security_NIT.pdf",
        "total_pages": 6,
        "extraction_status": "READY",
        "next_clause_seq": {"TECH": 7, "FIN": 2, "STAT": 2, "EXP": 1, "DEL": 1, "GEN": 1},
        "bidders": [
            {"company_name": "CyberShield Defense Technologies Pvt Ltd", "final_status": "QUALIFIED"},
            {"company_name": "QuantumNet Solutions India Ltd", "final_status": "UNDER_REVIEW"},
        ],
        "clauses": [
            {
                "clause_code": "NET-01",
                "category": "TECHNICAL",
                "title": "Firewall Throughput & Inspection",
                "description": "Next-generation firewall throughput of minimum 40 Gbps under full threat protection",
                "source_text": "The supplied firewall appliance must deliver a minimum next-generation firewall throughput of 40 Gbps under full threat protection.",
                "is_mandatory": True,
                "page_number": 1,
                "rule_config": {"type": "NUMERIC_MIN", "parameter": "firewall_throughput", "value": 40, "unit": "Gbps"},
            },
            {
                "clause_code": "NET-02",
                "category": "TECHNICAL",
                "title": "High-Density 10G SFP+ Interfaces",
                "description": "Minimum 8 dedicated 10 Gbps SFP+ optical transceiver interfaces",
                "source_text": "System must provide at least 8 dedicated 10 Gbps SFP+ transceiver interfaces.",
                "is_mandatory": True,
                "page_number": 2,
                "rule_config": {"type": "NUMERIC_MIN", "parameter": "sfp_interfaces", "value": 8, "unit": "ports"},
            },
            {
                "clause_code": "NET-03",
                "category": "TECHNICAL",
                "title": "3-Year Comprehensive OEM Warranty",
                "description": "3-year 24x7 on-site OEM hardware and firmware warranty with 4-hour MTTR",
                "source_text": "A comprehensive on-site OEM warranty of 3 years with 24x7 hardware replacement must be provided.",
                "is_mandatory": True,
                "page_number": 2,
                "rule_config": {"type": "NUMERIC_MIN", "parameter": "warranty_years", "value": 3, "unit": "years"},
            },
            {
                "clause_code": "NET-04",
                "category": "TECHNICAL",
                "title": "Native IPv6 Protocol Dual-Stack",
                "description": "Full compliance with IPv6 dual-stack routing and packet inspection",
                "source_text": "The equipment must support native IPv6 and IPv4 dual-stack routing with full feature parity.",
                "is_mandatory": True,
                "page_number": 3,
                "rule_config": {"type": "DOCUMENT_REQUIRED", "parameter": "ipv6_compliance", "value": None},
            },
            {
                "clause_code": "NET-05",
                "category": "TECHNICAL",
                "title": "High Availability Active-Passive Failover",
                "description": "Stateful high-availability failover within 500 milliseconds",
                "source_text": "Appliance must support stateful high availability in active-passive clustering mode with automated failover.",
                "is_mandatory": True,
                "page_number": 3,
                "rule_config": {"type": "DOCUMENT_REQUIRED", "parameter": "ha_failover", "value": None},
            },
            {
                "clause_code": "NET-06",
                "category": "TECHNICAL",
                "title": "Integrated IPS/IDS Threat Engine",
                "description": "Hardware-accelerated Intrusion Prevention and Detection engine",
                "source_text": "The platform must incorporate a hardware-accelerated IPS/IDS engine with daily automated signature updates.",
                "is_mandatory": True,
                "page_number": 4,
                "rule_config": {"type": "DOCUMENT_REQUIRED", "parameter": "ips_ids_engine", "value": None},
            },
            {
                "clause_code": "NET-07",
                "category": "DELIVERY_SLA",
                "title": "Annual Support SLA Guarantee",
                "description": "24x7 enterprise technical support agreement with 4-hour MTTR",
                "source_text": "OEM must provide an enterprise support service level agreement with 4-hour mean time to resolution.",
                "is_mandatory": True,
                "page_number": 4,
                "rule_config": {"type": "DOCUMENT_REQUIRED", "parameter": "support_sla", "value": None},
            },
            {
                "clause_code": "NET-08",
                "category": "FINANCIAL",
                "title": "Minimum Average Annual Turnover",
                "description": "Average annual turnover of at least INR 3.0 Crores in last 3 financial years",
                "source_text": "Bidder must have an average annual turnover of at least INR 3.0 Crores during the last three financial years.",
                "is_mandatory": True,
                "page_number": 5,
                "rule_config": {"type": "NUMERIC_MIN", "parameter": "average_annual_turnover", "value": 3.0, "unit": "Crores"},
            },
            {
                "clause_code": "NET-09",
                "category": "STATUTORY",
                "title": "Make in India (MII) Local Content",
                "description": "Minimum 50% domestic value addition / Class-I local content declaration",
                "source_text": "The bidder must submit a Class-I local supplier certificate confirming minimum 50% local content.",
                "is_mandatory": True,
                "page_number": 6,
                "rule_config": {"type": "NUMERIC_MIN", "parameter": "local_content_percentage", "value": 50, "unit": "%"},
            },
        ],
    },
    {
        "gem_tender_id": "GEM/2026/B/8912452",
        "title": "Industrial UPS & Power Backup Systems Procurement",
        "file_name": "GEM_2026_B_8912452_Industrial_UPS_NIT.pdf",
        "total_pages": 5,
        "extraction_status": "READY",
        "next_clause_seq": {"TECH": 7, "FIN": 2, "STAT": 2, "EXP": 1, "DEL": 1, "GEN": 1},
        "bidders": [
            {"company_name": "PowerGrid Dynamics India Pvt Ltd", "final_status": "QUALIFIED"},
            {"company_name": "Voltech Heavy Industrial Energy Corp", "final_status": "UNDER_REVIEW"},
        ],
        "clauses": [
            {
                "clause_code": "UPS-01",
                "category": "TECHNICAL",
                "title": "Three-Phase Online UPS Capacity",
                "description": "Minimum 500 kVA online double-conversion industrial UPS system",
                "source_text": "The UPS system must have a rated capacity of at least 500 kVA with true online double-conversion topology.",
                "is_mandatory": True,
                "page_number": 1,
                "rule_config": {"type": "NUMERIC_MIN", "parameter": "ups_capacity", "value": 500, "unit": "kVA"},
            },
            {
                "clause_code": "UPS-02",
                "category": "TECHNICAL",
                "title": "Full-Load Operating Efficiency",
                "description": "Overall electrical efficiency of at least 95% at full rated load",
                "source_text": "The system efficiency must be greater than or equal to 95% under 100% rated linear load.",
                "is_mandatory": True,
                "page_number": 1,
                "rule_config": {"type": "NUMERIC_MIN", "parameter": "efficiency_pct", "value": 95, "unit": "%"},
            },
            {
                "clause_code": "UPS-03",
                "category": "TECHNICAL",
                "title": "VRLA Battery Autonomy Backup",
                "description": "Minimum 30 minutes continuous battery autonomy at 100% load",
                "source_text": "Battery bank must ensure at least 30 minutes of continuous backup at full 500 kVA load.",
                "is_mandatory": True,
                "page_number": 2,
                "rule_config": {"type": "NUMERIC_MIN", "parameter": "battery_backup_minutes", "value": 30, "unit": "minutes"},
            },
            {
                "clause_code": "UPS-04",
                "category": "TECHNICAL",
                "title": "3-Year Comprehensive On-Site Warranty",
                "description": "3-year comprehensive on-site warranty for UPS unit and battery banks",
                "source_text": "Bidder shall provide a comprehensive on-site warranty of 3 years covering electronics and battery racks.",
                "is_mandatory": True,
                "page_number": 2,
                "rule_config": {"type": "NUMERIC_MIN", "parameter": "warranty_years", "value": 3, "unit": "years"},
            },
            {
                "clause_code": "UPS-05",
                "category": "TECHNICAL",
                "title": "Remote SNMP & Cloud Telemetry",
                "description": "Real-time network telemetry with remote shutdown and SNMP v3 card",
                "source_text": "UPS must include an integrated SNMP v3 card and Modbus TCP interface for centralized remote monitoring.",
                "is_mandatory": True,
                "page_number": 3,
                "rule_config": {"type": "DOCUMENT_REQUIRED", "parameter": "remote_snmp", "value": None},
            },
            {
                "clause_code": "UPS-06",
                "category": "TECHNICAL",
                "title": "Overload Protection & Static Bypass",
                "description": "Automated seamless static bypass switch and 150% overload capability",
                "source_text": "System must withstand 150% overload for 1 minute with automatic zero-transfer static bypass switch.",
                "is_mandatory": True,
                "page_number": 3,
                "rule_config": {"type": "DOCUMENT_REQUIRED", "parameter": "static_bypass", "value": None},
            },
            {
                "clause_code": "UPS-07",
                "category": "FINANCIAL",
                "title": "Minimum Average Annual Turnover",
                "description": "Average turnover of at least INR 4.0 Crores during last 3 fiscal years",
                "source_text": "Bidder must demonstrate an average annual turnover of at least INR 4.0 Crores across the last 3 financial years.",
                "is_mandatory": True,
                "page_number": 4,
                "rule_config": {"type": "NUMERIC_MIN", "parameter": "average_annual_turnover", "value": 4.0, "unit": "Crores"},
            },
            {
                "clause_code": "UPS-08",
                "category": "STATUTORY",
                "title": "BIS Standards Certification",
                "description": "Compliance with IS 16242 industrial safety and BIS certification",
                "source_text": "Equipment must possess valid BIS certification adhering to IS 16242 standards.",
                "is_mandatory": True,
                "page_number": 5,
                "rule_config": {"type": "DOCUMENT_REQUIRED", "parameter": "bis_cert", "value": None},
            },
        ],
    },
    {
        "gem_tender_id": "GEM/2026/B/8912453",
        "title": "Petroleum Storage Monitoring & Safety Equipment Procurement",
        "file_name": "GEM_2026_B_8912453_Petroleum_Safety_NIT.pdf",
        "total_pages": 7,
        "extraction_status": "READY",
        "next_clause_seq": {"TECH": 7, "FIN": 2, "STAT": 2, "EXP": 2, "DEL": 1, "GEN": 1},
        "bidders": [
            {"company_name": "HydroSafe Safety Instrumentation Ltd", "final_status": "QUALIFIED"},
            {"company_name": "PetroSense Automation India Pvt Ltd", "final_status": "UNDER_REVIEW"},
            {"company_name": "Vanguard Fluid Safety Systems", "final_status": "DISQUALIFIED"},
        ],
        "clauses": [
            {
                "clause_code": "PET-01",
                "category": "TECHNICAL",
                "title": "Radar Tank-Level Continuous Gauging",
                "description": "Non-contact FMCW radar level transmitter with custody transfer precision",
                "source_text": "Non-contact FMCW radar gauge must deliver continuous level monitoring with accuracy within +/- 1 mm.",
                "is_mandatory": True,
                "page_number": 1,
                "rule_config": {"type": "DOCUMENT_REQUIRED", "parameter": "radar_level_gauging", "value": None},
            },
            {
                "clause_code": "PET-02",
                "category": "TECHNICAL",
                "title": "Hydrocarbon Vapor Leak Detection",
                "description": "Optical infrared hydrocarbon gas leak sensors with audible alarm",
                "source_text": "Fixed infrared hydrocarbon leak detectors must trigger automated audio-visual alarms within 5 seconds.",
                "is_mandatory": True,
                "page_number": 2,
                "rule_config": {"type": "DOCUMENT_REQUIRED", "parameter": "leak_detection", "value": None},
            },
            {
                "clause_code": "PET-03",
                "category": "TECHNICAL",
                "title": "Multi-Point Storage Temperature Profiling",
                "description": "Continuous multi-element RTD temperature probe inside terminal tanks",
                "source_text": "A multi-spot RTD temperature sensor probe must measure product temperature profile across tank height.",
                "is_mandatory": True,
                "page_number": 2,
                "rule_config": {"type": "DOCUMENT_REQUIRED", "parameter": "temp_monitoring", "value": None},
            },
            {
                "clause_code": "PET-04",
                "category": "TECHNICAL",
                "title": "Explosion-Safe ATEX / PESO Certification",
                "description": "Flameproof Ex-d and Intrinsic Safety Ex-ia certified field sensors",
                "source_text": "All field-installed equipment must hold PESO and ATEX Zone 0/1 flameproof certifications.",
                "is_mandatory": True,
                "page_number": 3,
                "rule_config": {"type": "DOCUMENT_REQUIRED", "parameter": "explosion_safe_cert", "value": None},
            },
            {
                "clause_code": "PET-05",
                "category": "TECHNICAL",
                "title": "2-Year Comprehensive OEM Warranty",
                "description": "Minimum 2-year on-site comprehensive warranty with quarterly calibration",
                "source_text": "The bidder must furnish a 2-year comprehensive on-site OEM warranty including sensor replacements.",
                "is_mandatory": True,
                "page_number": 3,
                "rule_config": {"type": "NUMERIC_MIN", "parameter": "warranty_years", "value": 2, "unit": "years"},
            },
            {
                "clause_code": "PET-06",
                "category": "TECHNICAL",
                "title": "Remote Alert & Emergency Shutdown Telemetry",
                "description": "Real-time automated alarms and emergency shutdown (ESD) relay",
                "source_text": "System must integrate with facility SCADA via Modbus-TCP and provide dry contact outputs for emergency shutdown.",
                "is_mandatory": True,
                "page_number": 4,
                "rule_config": {"type": "DOCUMENT_REQUIRED", "parameter": "emergency_shutdown", "value": None},
            },
            {
                "clause_code": "PET-07",
                "category": "FINANCIAL",
                "title": "Minimum Average Annual Turnover",
                "description": "Average turnover of at least INR 6.0 Crores during last 3 fiscal years",
                "source_text": "Average annual turnover of the bidder during the last three financial years must be at least INR 6.0 Crores.",
                "is_mandatory": True,
                "page_number": 5,
                "rule_config": {"type": "NUMERIC_MIN", "parameter": "average_annual_turnover", "value": 6.0, "unit": "Crores"},
            },
            {
                "clause_code": "PET-08",
                "category": "STATUTORY",
                "title": "PESO Authorized OEM Certification",
                "description": "Valid statutory PESO manufacturing license and test certificate",
                "source_text": "Bidder or OEM must possess a valid PESO manufacturing license and factory compliance authorization.",
                "is_mandatory": True,
                "page_number": 5,
                "rule_config": {"type": "DOCUMENT_REQUIRED", "parameter": "peso_license", "value": None},
            },
            {
                "clause_code": "PET-09",
                "category": "EXPERIENCE",
                "title": "Past Petroleum Automation Contracts",
                "description": "Successful completion of at least 2 similar hydrocarbon terminal contracts",
                "source_text": "Bidder must have completed at least 2 similar petroleum terminal telemetry projects in the last 5 years.",
                "is_mandatory": True,
                "page_number": 6,
                "rule_config": {"type": "NUMERIC_MIN", "parameter": "similar_contracts_count", "value": 2, "unit": "contracts"},
            },
            {
                "clause_code": "PET-10",
                "category": "DELIVERY_SLA",
                "title": "Field Delivery & Commissioning Schedule",
                "description": "Delivery, installation, and field commissioning within 45 days",
                "source_text": "All monitoring hardware must be supplied, installed, and commissioned within 45 calendar days.",
                "is_mandatory": True,
                "page_number": 7,
                "rule_config": {"type": "NUMERIC_MAX", "parameter": "delivery_days", "value": 45, "unit": "days"},
            },
        ],
    },
    {
        "gem_tender_id": "GEM/2026/B/8912454",
        "title": "Automated Water Quality Monitoring Systems Procurement",
        "file_name": "GEM_2026_B_8912454_Water_Monitoring_NIT.pdf",
        "total_pages": 4,
        "extraction_status": "READY",
        "next_clause_seq": {"TECH": 6, "FIN": 2, "STAT": 1, "EXP": 1, "DEL": 1, "GEN": 1},
        "bidders": [
            {"company_name": "AquaPure Environmental Sensors Pvt Ltd", "final_status": "QUALIFIED"},
            {"company_name": "EnviroTech Analytics India Ltd", "final_status": "UNDER_REVIEW"},
        ],
        "clauses": [
            {
                "clause_code": "WAT-01",
                "category": "TECHNICAL",
                "title": "Continuous pH Range Monitoring",
                "description": "Automated glass electrode pH sensor covering 0 to 14 pH with 0.01 resolution",
                "source_text": "The analyzer must measure pH continuously across 0 to 14 pH range with precision of +/- 0.05 pH.",
                "is_mandatory": True,
                "page_number": 1,
                "rule_config": {"type": "DOCUMENT_REQUIRED", "parameter": "ph_monitoring", "value": None},
            },
            {
                "clause_code": "WAT-02",
                "category": "TECHNICAL",
                "title": "Optical Turbidity Sensor Measurement",
                "description": "Nephelometric laser turbidity measurement covering 0 to 1000 NTU",
                "source_text": "Turbidity sensor must operate on 90-degree scattered light technology measuring up to 1000 NTU.",
                "is_mandatory": True,
                "page_number": 1,
                "rule_config": {"type": "DOCUMENT_REQUIRED", "parameter": "turbidity_monitoring", "value": None},
            },
            {
                "clause_code": "WAT-03",
                "category": "TECHNICAL",
                "title": "Total Dissolved Solids (TDS) Measurement",
                "description": "Electrolytic automated TDS measurement (0-5000 mg/L)",
                "source_text": "Instrument must deliver automated continuous TDS measurement spanning 0 to 5000 mg/L.",
                "is_mandatory": True,
                "page_number": 2,
                "rule_config": {"type": "DOCUMENT_REQUIRED", "parameter": "tds_measurement", "value": None},
            },
            {
                "clause_code": "WAT-04",
                "category": "TECHNICAL",
                "title": "4G/GPRS Cloud Telemetry",
                "description": "Continuous cellular transmission to central pollution control dashboard",
                "source_text": "Station must feature integrated 4G/GPRS telemetry with direct data streaming to CPCB/SPCB servers.",
                "is_mandatory": True,
                "page_number": 2,
                "rule_config": {"type": "DOCUMENT_REQUIRED", "parameter": "remote_telemetry", "value": None},
            },
            {
                "clause_code": "WAT-05",
                "category": "TECHNICAL",
                "title": "Operating Temperature Range",
                "description": "Field weather resistance spanning -5°C to 55°C operating range",
                "source_text": "Sensors and controller enclosure must operate reliably between -5°C and 55°C with IP66 ingress protection.",
                "is_mandatory": True,
                "page_number": 3,
                "rule_config": {"type": "DOCUMENT_REQUIRED", "parameter": "temp_range", "value": None},
            },
            {
                "clause_code": "WAT-06",
                "category": "TECHNICAL",
                "title": "2-Year Comprehensive OEM Warranty",
                "description": "2-year comprehensive on-site warranty covering all analyzer modules",
                "source_text": "Bidder shall provide a comprehensive on-site OEM warranty of 2 years covering analyzer and sensor units.",
                "is_mandatory": True,
                "page_number": 3,
                "rule_config": {"type": "NUMERIC_MIN", "parameter": "warranty_years", "value": 2, "unit": "years"},
            },
            {
                "clause_code": "WAT-07",
                "category": "DELIVERY_SLA",
                "title": "Annual Recalibration Support & Supplies",
                "description": "Bi-annual on-site calibration check and standard reagent buffer refills",
                "source_text": "Contract includes bi-annual sensor recalibration visits and replacement standard calibration buffer solutions.",
                "is_mandatory": True,
                "page_number": 4,
                "rule_config": {"type": "DOCUMENT_REQUIRED", "parameter": "calibration_support", "value": None},
            },
        ],
    },
]


async def seed_additional_demo_tenders(db):
    """Idempotently seed the 4 additional sandbox demonstration tenders."""
    for tender_data in ADDITIONAL_DEMO_TENDERS:
        stmt = select(Tender).where(Tender.gem_tender_id == tender_data["gem_tender_id"])
        existing_t = (await db.execute(stmt)).scalar_one_or_none()
        if existing_t:
            t_obj = existing_t
            logger.info(f"Existing demo tender found: {t_obj.gem_tender_id} ({t_obj.title})")
        else:
            t_obj = Tender(
                title=tender_data["title"],
                gem_tender_id=tender_data["gem_tender_id"],
                file_name=tender_data["file_name"],
                total_pages=tender_data["total_pages"],
                extraction_status=tender_data["extraction_status"],
                next_clause_seq=tender_data["next_clause_seq"],
            )
            db.add(t_obj)
            await db.flush()
            logger.info(f"Created demo tender: {t_obj.gem_tender_id} ({t_obj.title})")

        # Seed clauses
        c_stmt = select(TenderClause.clause_code).where(TenderClause.tender_id == t_obj.id)
        existing_codes = set((await db.execute(c_stmt)).scalars().all())
        for c_item in tender_data["clauses"]:
            if c_item["clause_code"] not in existing_codes:
                clause = TenderClause(
                    tender_id=t_obj.id,
                    clause_code=c_item["clause_code"],
                    category=c_item["category"],
                    title=c_item["title"],
                    description=c_item["description"],
                    source_text=c_item["source_text"],
                    page_number=c_item["page_number"],
                    is_mandatory=c_item["is_mandatory"],
                    rule_config=c_item["rule_config"],
                    is_confirmed=True,
                )
                db.add(clause)

        # Seed bidders
        b_stmt = select(Bidder.company_name).where(Bidder.tender_id == t_obj.id)
        existing_bidders = set((await db.execute(b_stmt)).scalars().all())
        for b_item in tender_data["bidders"]:
            if b_item["company_name"] not in existing_bidders:
                bidder = Bidder(
                    tender_id=t_obj.id,
                    company_name=b_item["company_name"],
                    final_status=b_item["final_status"],
                )
                db.add(bidder)

        await db.commit()
    logger.info("All 4 additional demo tenders verified and confirmed.")


async def seed_golden_demo() -> str:
    await init_db()

    async with database.AsyncSessionLocal() as db:
        # 1. Idempotent Tender Check
        stmt = select(Tender).where(Tender.gem_tender_id == "GEM/2026/B/8912450")
        existing_tender = (await db.execute(stmt)).scalar_one_or_none()

        if existing_tender:
            tender = existing_tender
            logger.info(f"Existing Golden Demo Tender found: {tender.id} ({tender.gem_tender_id})")
        else:
            tender = Tender(
                title="Server Compute Infrastructure & Datacenter Equipment Procurement",
                gem_tender_id="GEM/2026/B/8912450",
                file_name="GEM_2026_B_8912450_Tender_Notice.pdf",
                total_pages=4,
                extraction_status="READY",
                next_clause_seq={"TECH": 4, "FIN": 5, "STAT": 3, "EXP": 2, "DEL": 2, "GEN": 1},
            )
            db.add(tender)
            await db.flush()
            logger.info(f"Created Golden Demo Tender: {tender.id} ({tender.gem_tender_id})")

        # 2. Idempotent Clause Insertion
        c_stmt = select(TenderClause).where(TenderClause.tender_id == tender.id)
        existing_clauses = (await db.execute(c_stmt)).scalars().all()
        existing_codes = {c.clause_code for c in existing_clauses}

        for item in BENCHMARK_CLAUSES:
            if item["clause_code"] not in existing_codes:
                clause = TenderClause(
                    tender_id=tender.id,
                    clause_code=item["clause_code"],
                    category=item["category"],
                    title=item["title"],
                    description=item["description"],
                    source_text=item["source_text"],
                    page_number=item["page_number"],
                    is_mandatory=item["is_mandatory"],
                    rule_config=item["rule_config"],
                    is_confirmed=True,
                )
                db.add(clause)
        await db.commit()
        logger.info(f"Confirmed 11 Benchmark Clauses for tender {tender.id}")

        # 3. Load Demo Bidders (A, B, C)
        logger.info(f"Loading Demo Bidders A, B, and C for tender {tender.id}...")
        bidders_resp = await load_demo_bidders(tender.id, db=db)
        logger.info(f"Loaded {bidders_resp.bidders_count} bidders: {bidders_resp.message}")

        # 4. Run Compliance Evaluation
        logger.info(f"Running compliance evaluation across all bidders for tender {tender.id}...")
        eval_resp = await run_tender_compliance_evaluation(
            tender_id=tender.id,
            req=EvaluationRunRequest(use_live_llm=False),
            db=db,
        )
        logger.info(f"Evaluation complete: {eval_resp.total_evaluations} evaluations produced across {len(eval_resp.reports)} bidders.")

        for r in eval_resp.reports:
            logger.info(
                f"  * Bidder {r.bidder_id}: PASS={r.pass_count}, FAIL={r.fail_count}, REVIEW={r.review_count} "
                f"-> Recommendation: {r.officer_recommendation}"
            )

        # 5. Seed 4 Additional Sandbox Demonstration Tenders
        await seed_additional_demo_tenders(db)

        return str(tender.id)


if __name__ == "__main__":
    tender_id = asyncio.run(seed_golden_demo())
    print("\n" + "=" * 60)
    print("GOLDEN DEMO SEED COMPLETED SUCCESSFULLY!")
    print(f"Golden Tender ID: {tender_id}")
    print("Direct URLs:")
    print(f"  * Dashboard & Compliance Matrix: http://localhost:3000/tenders/{tender_id}/compliance")
    print(f"  * Bidder Proposals & Documents: http://localhost:3000/tenders/{tender_id}/bidders")
    print(f"  * Extracted Tender Requirements: http://localhost:3000/tenders/{tender_id}/clauses")
    print("=" * 60 + "\n")

