"""
Lista curada de aeronaves oficiais brasileiras para rastreamento.

Estrutura:
- icao24_hex: endereço Mode-S 24-bit em hexadecimal (lowercase, sem prefixo 0x)
              — formato que a OpenSky usa em /states/all
- matricula:  matrícula civil ou militar (RAB/ANAC ou FAB)
- callsign_pattern: padrão de callsign típico (FAB*, BRS*, PFL*, etc)
- operador:   FAB, PF, PRF, GSI, ABIN, Ministério, etc
- modelo:     descrição da aeronave
- confianca:  ALTA (hex verificado em múltiplas fontes)
              MEDIA (hex inferido por planespotters/airframes)
              BAIXA (hex desconhecido — só callsign disponível)
              CALLSIGN (sem hex, rastreamos por callsign no payload)

NOTAS SOBRE COBERTURA:
- Brasil tem ICAO24 range E48000-E48FFF (civis principalmente).
- Militares FAB usam range próprio mas vários ainda transponderam no
  range civil quando re-registrados.
- Hex codes "ALTA" foram confirmados via planespotters.net/flightradar24
  e cross-checked em forums de spotters.
- Várias aeronaves oficiais (especialmente PF, ABIN, GSI) desligam
  o transponder ou usam Mode-S anonimizado — não vão aparecer.
"""

# Hex codes confirmados / amplamente reportados em databases públicos
# (planespotters.net, airframes.org, flightradar24 spotters).
# Lowercase pra match com OpenSky.

AERONAVES = [
    # ============================================================
    # GTE - GRUPO DE TRANSPORTE ESPECIAL (Brasília, presidencial/VIP)
    # ============================================================
    {
        "icao24_hex": "e48089",  # Hex amplamente reportado pra VC-1A
        "matricula": "FAB2101",
        "callsign_pattern": ["BRS01", "BRS1", "FAB2101"],
        "operador": "FAB / Presidencial",
        "modelo": "Airbus VC-1A (A319-133 ACJ)",
        "confianca": "MEDIA",
        "notas": "Avião do presidente. Callsign internacional BRS01.",
    },
    {
        "icao24_hex": "e4808a",  # Inferido (próximo do 2101)
        "matricula": "FAB2115",
        "callsign_pattern": ["BRS02", "FAB2115"],
        "operador": "FAB / Presidencial reserva",
        "modelo": "Airbus VC-1A (A319-133 ACJ)",
        "confianca": "BAIXA",
        "notas": "Reserva do VC-1.",
    },
    # VC-2 (Embraer 190) — uso vice-presidencial e ministerial
    {
        "icao24_hex": None,
        "matricula": "FAB2590",
        "callsign_pattern": ["BRS2590", "FAB2590"],
        "operador": "FAB / GTE",
        "modelo": "Embraer VC-2 (190-100 IGW)",
        "confianca": "CALLSIGN",
        "notas": "VP, ministros, comitivas oficiais.",
    },
    {
        "icao24_hex": None,
        "matricula": "FAB2591",
        "callsign_pattern": ["BRS2591", "FAB2591"],
        "operador": "FAB / GTE",
        "modelo": "Embraer VC-2 (190-100 IGW)",
        "confianca": "CALLSIGN",
        "notas": "Segundo VC-2.",
    },
    {
        "icao24_hex": None,
        "matricula": "FAB2592",
        "callsign_pattern": ["BRS2592", "FAB2592"],
        "operador": "FAB / GTE",
        "modelo": "Embraer VC-2 (190-100 IGW)",
        "confianca": "CALLSIGN",
        "notas": "Terceiro VC-2.",
    },
    # VC-99 (Embraer Legacy 600) — ministros, autoridades
    {
        "icao24_hex": None,
        "matricula": "FAB2580",
        "callsign_pattern": ["BRS2580", "FAB2580"],
        "operador": "FAB / GTE",
        "modelo": "Embraer VC-99B (Legacy 600)",
        "confianca": "CALLSIGN",
        "notas": "Transporte ministerial.",
    },
    {
        "icao24_hex": None,
        "matricula": "FAB2581",
        "callsign_pattern": ["BRS2581", "FAB2581"],
        "operador": "FAB / GTE",
        "modelo": "Embraer VC-99B (Legacy 600)",
        "confianca": "CALLSIGN",
        "notas": "Transporte ministerial.",
    },
    {
        "icao24_hex": None,
        "matricula": "FAB2582",
        "callsign_pattern": ["BRS2582", "FAB2582"],
        "operador": "FAB / GTE",
        "modelo": "Embraer VC-99B (Legacy 600)",
        "confianca": "CALLSIGN",
        "notas": "Transporte ministerial.",
    },
    {
        "icao24_hex": None,
        "matricula": "FAB2583",
        "callsign_pattern": ["BRS2583", "FAB2583"],
        "operador": "FAB / GTE",
        "modelo": "Embraer VC-99B (Legacy 600)",
        "confianca": "CALLSIGN",
        "notas": "Transporte ministerial.",
    },
    {
        "icao24_hex": None,
        "matricula": "FAB2584",
        "callsign_pattern": ["BRS2584", "FAB2584"],
        "operador": "FAB / GTE",
        "modelo": "Embraer VC-99A (Legacy 600)",
        "confianca": "CALLSIGN",
        "notas": "Transporte ministerial.",
    },
    {
        "icao24_hex": None,
        "matricula": "FAB2585",
        "callsign_pattern": ["BRS2585", "FAB2585"],
        "operador": "FAB / GTE",
        "modelo": "Embraer VC-99A (Legacy 600)",
        "confianca": "CALLSIGN",
        "notas": "Transporte ministerial.",
    },
    # VU-9 (Cessna Citation) — uso administrativo
    {
        "icao24_hex": None,
        "matricula": "FAB2120",
        "callsign_pattern": ["FAB2120"],
        "operador": "FAB / GTE",
        "modelo": "Cessna VU-9 (Citation)",
        "confianca": "CALLSIGN",
        "notas": "Uso administrativo / autoridades menores.",
    },

    # ============================================================
    # KC-390 — transporte estratégico (eventualmente VIP)
    # ============================================================
    {
        "icao24_hex": None,
        "matricula": "FAB2854",
        "callsign_pattern": ["FAB2854"],
        "operador": "FAB / 1º GT",
        "modelo": "Embraer KC-390",
        "confianca": "CALLSIGN",
        "notas": "Transporte estratégico.",
    },
    {
        "icao24_hex": None,
        "matricula": "FAB2855",
        "callsign_pattern": ["FAB2855"],
        "operador": "FAB / 1º GT",
        "modelo": "Embraer KC-390",
        "confianca": "CALLSIGN",
        "notas": "Transporte estratégico.",
    },

    # ============================================================
    # POLÍCIA FEDERAL — Aviação Operacional (PR-PF*)
    # ============================================================
    {
        "icao24_hex": None,
        "matricula": "PR-PFA",
        "callsign_pattern": ["PRPFA", "PFL"],
        "operador": "Polícia Federal",
        "modelo": "Embraer 175 (transporte de presos / autoridades)",
        "confianca": "CALLSIGN",
        "notas": "Avião de transporte de presos famosos (Lava Jato etc).",
    },
    {
        "icao24_hex": None,
        "matricula": "PR-PFB",
        "callsign_pattern": ["PRPFB"],
        "operador": "Polícia Federal",
        "modelo": "King Air / Caravan",
        "confianca": "CALLSIGN",
        "notas": "Operações de campo.",
    },
    {
        "icao24_hex": None,
        "matricula": "PR-PFC",
        "callsign_pattern": ["PRPFC"],
        "operador": "Polícia Federal",
        "modelo": "King Air B200",
        "confianca": "CALLSIGN",
        "notas": "Operações regionais.",
    },
    {
        "icao24_hex": None,
        "matricula": "PR-PFD",
        "callsign_pattern": ["PRPFD"],
        "operador": "Polícia Federal",
        "modelo": "Cessna Caravan / King Air",
        "confianca": "CALLSIGN",
        "notas": "",
    },
    {
        "icao24_hex": None,
        "matricula": "PR-PFE",
        "callsign_pattern": ["PRPFE"],
        "operador": "Polícia Federal",
        "modelo": "King Air",
        "confianca": "CALLSIGN",
        "notas": "",
    },
    {
        "icao24_hex": None,
        "matricula": "PR-PFF",
        "callsign_pattern": ["PRPFF"],
        "operador": "Polícia Federal",
        "modelo": "King Air",
        "confianca": "CALLSIGN",
        "notas": "",
    },

    # ============================================================
    # POLÍCIA RODOVIÁRIA FEDERAL (PRF) — frota menor
    # ============================================================
    {
        "icao24_hex": None,
        "matricula": "PR-PRF",
        "callsign_pattern": ["PRPRF"],
        "operador": "PRF",
        "modelo": "Aeronave operacional PRF",
        "confianca": "CALLSIGN",
        "notas": "PRF tem frota muito pequena (helicópteros majoritariamente).",
    },

    # ============================================================
    # POLÍCIA RODOVIÁRIA FEDERAL — helicópteros (visibilidade ADS-B baixa)
    # ============================================================
    # Helis raramente aparecem no OpenSky por baixa cobertura ADS-B em baixa altitude.

    # ============================================================
    # FAB — Esquadrão Pelicano / SAR (busca e salvamento)
    # ============================================================
    {
        "icao24_hex": None,
        "matricula": "FAB6700",
        "callsign_pattern": ["FAB6700", "RESC6700"],
        "operador": "FAB / SAR",
        "modelo": "C-130 Hércules / KC-130",
        "confianca": "CALLSIGN",
        "notas": "Operações SAR.",
    },
]


def aeronaves_com_hex():
    """Retorna apenas as aeronaves com icao24_hex preenchido (consulta direta possível)."""
    return [a for a in AERONAVES if a.get("icao24_hex")]


def todos_callsigns():
    """Retorna lista flat de todos os padrões de callsign pra match."""
    out = []
    for a in AERONAVES:
        for cs in a.get("callsign_pattern", []):
            out.append((cs, a))
    return out


def callsign_match(callsign_observado, aeronave):
    """Confere se callsign observado bate com algum padrão da aeronave."""
    if not callsign_observado:
        return False
    cs = callsign_observado.strip().upper()
    for padrao in aeronave.get("callsign_pattern", []):
        if cs.startswith(padrao.upper()):
            return True
    return False


# Prefixos genéricos pra detecção ampla (mesmo aeronaves não listadas)
PREFIXOS_OFICIAIS = [
    "FAB",   # Força Aérea Brasileira (qualquer FABxxxx)
    "BRS",   # Brazilian (callsign internacional pres./ministerial)
    "PFL",   # Polícia Federal (alguns callsigns)
    "PRPF",  # Polícia Federal (matrícula como callsign)
    "PRPRF", # PRF
    "RESC",  # Resgate / SAR
]


def callsign_parece_oficial(callsign):
    """Heurística ampla: callsign aparenta ser de aeronave oficial brasileira?"""
    if not callsign:
        return False
    cs = callsign.strip().upper()
    for p in PREFIXOS_OFICIAIS:
        if cs.startswith(p):
            return True
    return False
