"""Seed rows for the mock core banking system (CIF master).

Native fields; overlap/trap cases are documented per row and mirrored in
PLAN.md's overlap matrix. Names are structured SURNAME NAME, keys are clean.
"""

CIF_ROWS: list[dict] = [
    # A — ACME: in both silos, clean shared tax code; controlled by CIF-1005.
    {
        "CIF_ID": "CIF-1001",
        "CUST_TYPE": "O",
        "NAME_TXT": "ACME INDUSTRIES S.P.A.",
        "TAX_CODE": "IT01234567890",
        "LEI_CODE": "529900ACME000000IT01",
        "BIRTH_DT": None,
        "INCORP_DT": "1998-05-12",
        "EMAIL_ADDR": "info@acme-industries.it",
        "CONTROLLING_CIF_ID": "CIF-1005",
    },
    # B — Mario Rossi: in both silos; CRM stores the tax code dirty.
    {
        "CIF_ID": "CIF-1002",
        "CUST_TYPE": "P",
        "NAME_TXT": "ROSSI MARIO",
        "TAX_CODE": "RSSMRA80A01H501U",
        "LEI_CODE": None,
        "BIRTH_DT": "1980-01-01",
        "INCORP_DT": None,
        "EMAIL_ADDR": "mario.rossi@example.com",
        "CONTROLLING_CIF_ID": None,
    },
    # C — Lucia Bianchi: in both silos, NO shared key (CRM has no tax code);
    # only name variant + same DOB + same email (different casing) correlate.
    {
        "CIF_ID": "CIF-1003",
        "CUST_TYPE": "P",
        "NAME_TXT": "BIANCHI LUCIA",
        "TAX_CODE": "BNCLCU85M41F205X",
        "LEI_CODE": None,
        "BIRTH_DT": "1985-08-01",
        "INCORP_DT": None,
        "EMAIL_ADDR": "lucia.bianchi@gmail.com",
        "CONTROLLING_CIF_ID": None,
    },
    # D — Ferrari Logistics: in both silos; CRM additionally holds a
    # near-duplicate account (typo, no tax code).
    {
        "CIF_ID": "CIF-1004",
        "CUST_TYPE": "O",
        "NAME_TXT": "FERRARI LOGISTICS S.R.L.",
        "TAX_CODE": "IT09876543210",
        "LEI_CODE": "529900FERRLOG000IT02",
        "BIRTH_DT": None,
        "INCORP_DT": "2005-11-03",
        "EMAIL_ADDR": "info@ferrarilogistics.it",
        "CONTROLLING_CIF_ID": None,
    },
    # E — Greenfield: core-banking only; controls ACME (beneficial owner demo).
    {
        "CIF_ID": "CIF-1005",
        "CUST_TYPE": "O",
        "NAME_TXT": "GREENFIELD CAPITAL HOLDING S.P.A.",
        "TAX_CODE": "IT05555555550",
        "LEI_CODE": "529900GREENCAP00IT03",
        "BIRTH_DT": None,
        "INCORP_DT": "1992-02-20",
        "EMAIL_ADDR": "holding@greenfieldcapital.it",
        "CONTROLLING_CIF_ID": None,
    },
    # F — Maria Rossi: sibling trap vs Mario Rossi (similar name, different
    # DOB/tax/email) — must stay NO_MATCH.
    {
        "CIF_ID": "CIF-1006",
        "CUST_TYPE": "P",
        "NAME_TXT": "ROSSI MARIA",
        "TAX_CODE": "RSSMRA82C45H501Y",
        "LEI_CODE": None,
        "BIRTH_DT": "1982-03-05",
        "INCORP_DT": None,
        "EMAIL_ADDR": "maria.rossi@libero.it",
        "CONTROLLING_CIF_ID": None,
    },
    # G — Giuseppe Verdi: in both silos with same name+DOB but different email
    # and no shared key -> lands in the POSSIBLE_MATCH band.
    {
        "CIF_ID": "CIF-1007",
        "CUST_TYPE": "P",
        "NAME_TXT": "VERDI GIUSEPPE",
        "TAX_CODE": "VRDGPP75D22F839K",
        "LEI_CODE": None,
        "BIRTH_DT": "1975-04-22",
        "INCORP_DT": None,
        "EMAIL_ADDR": "g.verdi@verdi-consulting.it",
        "CONTROLLING_CIF_ID": None,
    },
    # True negatives — core banking only.
    {
        "CIF_ID": "CIF-1008",
        "CUST_TYPE": "O",
        "NAME_TXT": "BANCA POPOLARE DEL LEVANTE S.P.A.",
        "TAX_CODE": "IT02222333440",
        "LEI_CODE": "529900BPLEVANTE0IT04",
        "BIRTH_DT": None,
        "INCORP_DT": "1954-06-30",
        "EMAIL_ADDR": "segreteria@bplevante.it",
        "CONTROLLING_CIF_ID": None,
    },
    {
        "CIF_ID": "CIF-1009",
        "CUST_TYPE": "P",
        "NAME_TXT": "ESPOSITO ANTONIO",
        "TAX_CODE": "SPSNTN71E15F839Q",
        "LEI_CODE": None,
        "BIRTH_DT": "1971-05-15",
        "INCORP_DT": None,
        "EMAIL_ADDR": "antonio.esposito@pec.it",
        "CONTROLLING_CIF_ID": None,
    },
    {
        "CIF_ID": "CIF-1010",
        "CUST_TYPE": "O",
        "NAME_TXT": "OLIVETTI MECCANICA S.R.L.",
        "TAX_CODE": "IT04444111220",
        "LEI_CODE": "529900OLIVMEC000IT05",
        "BIRTH_DT": None,
        "INCORP_DT": "1987-09-14",
        "EMAIL_ADDR": "info@olivettimeccanica.it",
        "CONTROLLING_CIF_ID": None,
    },
    {
        "CIF_ID": "CIF-1011",
        "CUST_TYPE": "P",
        "NAME_TXT": "COLOMBO FRANCESCA",
        "TAX_CODE": "CLMFNC88T50F205Z",
        "LEI_CODE": None,
        "BIRTH_DT": "1988-12-10",
        "INCORP_DT": None,
        "EMAIL_ADDR": "francesca.colombo@gmail.com",
        "CONTROLLING_CIF_ID": None,
    },
    {
        "CIF_ID": "CIF-1012",
        "CUST_TYPE": "O",
        "NAME_TXT": "TIRRENIA SHIPPING S.P.A.",
        "TAX_CODE": "IT06666777880",
        "LEI_CODE": "529900TIRSHIP000IT06",
        "BIRTH_DT": None,
        "INCORP_DT": "1978-03-02",
        "EMAIL_ADDR": "operations@tirreniashipping.it",
        "CONTROLLING_CIF_ID": None,
    },
    {
        "CIF_ID": "CIF-1013",
        "CUST_TYPE": "P",
        "NAME_TXT": "RICCI DAVIDE",
        "TAX_CODE": "RCCDVD79L20H501W",
        "LEI_CODE": None,
        "BIRTH_DT": "1979-07-20",
        "INCORP_DT": None,
        "EMAIL_ADDR": "d.ricci@studioricci.it",
        "CONTROLLING_CIF_ID": None,
    },
    {
        "CIF_ID": "CIF-1014",
        "CUST_TYPE": "O",
        "NAME_TXT": "AURORA ASSICURAZIONI S.P.A.",
        "TAX_CODE": "IT08888999000",
        "LEI_CODE": "529900AURORAASS0IT07",
        "BIRTH_DT": None,
        "INCORP_DT": "1969-01-25",
        "EMAIL_ADDR": "clienti@auroraassicurazioni.it",
        "CONTROLLING_CIF_ID": None,
    },
    # H — Sofia Greco: homonym-without-keys trap vs the CRM "Sofia Greco"
    # (different DOB, different email) — must stay NO_MATCH.
    {
        "CIF_ID": "CIF-1015",
        "CUST_TYPE": "P",
        "NAME_TXT": "GRECO SOFIA",
        "TAX_CODE": "GRCSFO88B52F839W",
        "LEI_CODE": None,
        "BIRTH_DT": "1988-02-12",
        "INCORP_DT": None,
        "EMAIL_ADDR": "sofia.greco@bluewin.ch",
        "CONTROLLING_CIF_ID": None,
    },
]
