"""Seed rows for the mock CRM (Salesforce-shaped Account).

Free-text names, inconsistent formatting, no LEI field at all. Overlap/trap
cases mirror PLAN.md's matrix and seeds/core_banking.py.
"""

ACCOUNT_ROWS: list[dict] = [
    # A — ACME: clean shared tax code with core banking.
    {
        "Id": "001A000001",
        "Type": "Business",
        "Name": "Acme Industries SpA",
        "TaxCode__c": "IT01234567890",
        "Birth_Date__c": None,
        "Email__c": "sales@acme-industries.it",
    },
    # B — Mario Rossi: same person as CIF-1002, tax code stored dirty.
    {
        "Id": "001A000002",
        "Type": "Person",
        "Name": "Mario Rossi",
        "TaxCode__c": " rssmra80a01h501u ",
        "Birth_Date__c": "1980-01-01",
        "Email__c": "mrossi80@gmail.com",
    },
    # C — Lucia Bianchi: same person as CIF-1003, NO tax code; correlates only
    # via name variant + DOB + email casing difference.
    {
        "Id": "001A000003",
        "Type": "Person",
        "Name": "Lucia Bianchi",
        "TaxCode__c": None,
        "Birth_Date__c": "1985-08-01",
        "Email__c": "Lucia.Bianchi@GMAIL.com",
    },
    # D — Ferrari Logistics, account 1: shared tax code with CIF-1004.
    {
        "Id": "001A000004",
        "Type": "Business",
        "Name": "Ferrari Logistics SRL",
        "TaxCode__c": "IT09876543210",
        "Birth_Date__c": None,
        "Email__c": "info@ferrarilogistics.it",
    },
    # D — Ferrari Logistics, account 2: near-duplicate inside the CRM
    # (typo in name, no tax code, same email) — must cluster with account 1.
    {
        "Id": "001A000005",
        "Type": "Business",
        "Name": "Ferrari Logistcs S.r.l.",
        "TaxCode__c": None,
        "Birth_Date__c": None,
        "Email__c": "info@ferrarilogistics.it",
    },
    # Homonym trap — a DIFFERENT Mario Rossi: identical name, different tax
    # code. The normalized key conflict must force NO_MATCH despite the name.
    {
        "Id": "001A000006",
        "Type": "Person",
        "Name": "Mario Rossi",
        "TaxCode__c": "RSSMRA80A01F205Z",
        "Birth_Date__c": "1980-01-11",
        "Email__c": "mario.rossi@studiorossi.it",
    },
    # G — Giuseppe Verdi: same name+DOB as CIF-1007, different email, no tax
    # code -> POSSIBLE_MATCH band.
    {
        "Id": "001A000007",
        "Type": "Person",
        "Name": "Giuseppe Verdi",
        "TaxCode__c": None,
        "Birth_Date__c": "1975-04-22",
        "Email__c": "giuseppe@verdiconsulting.com",
    },
    # True negatives — CRM only.
    {
        "Id": "001A000008",
        "Type": "Business",
        "Name": "startup innovativa XYZ srl",
        "TaxCode__c": None,
        "Birth_Date__c": None,
        "Email__c": "hello@startupxyz.io",
    },
    {
        "Id": "001A000009",
        "Type": "Person",
        "Name": "Chiara Fontana",
        "TaxCode__c": None,
        "Birth_Date__c": "1990-06-15",
        "Email__c": "chiara.fontana@outlook.com",
    },
    {
        "Id": "001A000010",
        "Type": "Business",
        "Name": "Mediterranea Import Export",
        "TaxCode__c": "IT07777888990",
        "Birth_Date__c": None,
        "Email__c": "info@medimpex.it",
    },
    # Fuzzy-negative trap: similar-ish name to Mario Rossi, everything else
    # different — fuzzy score must stay below the possible threshold.
    {
        "Id": "001A000011",
        "Type": "Person",
        "Name": "Marco Ross",
        "TaxCode__c": None,
        "Birth_Date__c": "1979-12-30",
        "Email__c": "marco.ross@yahoo.com",
    },
    {
        "Id": "001A000012",
        "Type": "Business",
        "Name": "Delta Consulting Group",
        "TaxCode__c": None,
        "Birth_Date__c": None,
        "Email__c": "contact@deltacg.com",
    },
    {
        "Id": "001A000013",
        "Type": "Person",
        "Name": "Alessandro Moretti",
        "TaxCode__c": None,
        "Birth_Date__c": "1968-09-09",
        "Email__c": "a.moretti@moretti.it",
    },
    {
        "Id": "001A000014",
        "Type": "Business",
        "Name": "Vesuvio Foods S.r.l.",
        "TaxCode__c": "IT03333222110",
        "Birth_Date__c": None,
        "Email__c": "orders@vesuviofoods.it",
    },
    # H — Sofia Greco: homonym-without-keys trap vs CIF-1015 (different DOB,
    # different email, no tax code) — must stay NO_MATCH.
    {
        "Id": "001A000015",
        "Type": "Person",
        "Name": "Sofia Greco",
        "TaxCode__c": None,
        "Birth_Date__c": "1991-02-12",
        "Email__c": "sofia.greco91@gmail.com",
    },
]
