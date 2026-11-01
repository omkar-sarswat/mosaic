"""Plain names for source systems, as an officer or a court would cite them.

Source codes stay in the database and the audit trail; reports and screens show the holder and the
register. A `-SYN` suffix marks the synthetic stand-in for that register.
"""

from __future__ import annotations

NAMES = {
    "UIDAI": "UIDAI Aadhaar e-KYC",
    "ITD": "Income Tax Department (PAN, returns)",
    "ECI": "Election Commission electoral roll",
    "PASSPORT": "Passport Seva",
    "SARATHI": "Sarathi driving licences",
    "VAHAN": "Vahan vehicle registration",
    "VAHAN-ANPR": "ANPR camera network",
    "NETC-FASTAG": "NETC FASTag toll reads",
    "TSP": "Telecom service provider subscriber records",
    "TSP-CDR": "Telecom call detail records",
    "BANK": "Bank statements",
    "BANK-KYC": "Bank KYC records",
    "BANK-HR": "Bank staff records",
    "FIU": "FIU-IND reports",
    "FIU-EGMONT": "FIU-IND Egmont exchange",
    "EXCHANGE": "Crypto exchange records",
    "CCTNS": "CCTNS crime records",
    "ZIPNET": "ZIPNET missing persons and vehicles",
    "I4C": "I4C cyber-crime reports (NCRP)",
    "CBI": "CBI case records",
    "NIA": "NIA case records",
    "NCB": "NCB case records",
    "NCB-CS-REG": "NCB controlled-substance register",
    "ED": "Enforcement Directorate records",
    "FSL": "Forensic science laboratory reports",
    "MCA": "MCA company registry",
    "GSTN": "GST network",
    "IGR": "Registration and stamps (property)",
    "PDS": "Public distribution system",
    "PFMS": "Public financial management system",
    "CPPP": "Central public procurement portal",
    "PNR": "Airline and rail reservations (PNR)",
    "PESO": "PESO explosives licences",
    "ARMS-LICENCE": "Arms licence register",
    "DEALER-REGISTER": "Dealer sales register",
    "CHARITY-COMM": "Charity Commissioner register",
    "HRMS": "Departmental HR records",
    "LGD": "Local Government Directory",
    "DRISHTI-ANALYTICS": "Mosaic typology alerts",
}


def source_name(code: str | None) -> str:
    """A readable name for a source code. The code itself (with its -SYN marker) stays in citations."""
    if not code:
        return "Unknown source"
    base = code[:-4] if code.endswith("-SYN") else code
    return NAMES.get(base) or NAMES.get(base.split(":")[0]) or base.replace("-", " ").title()
