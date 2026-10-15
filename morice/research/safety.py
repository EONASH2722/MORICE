"""Conservative intent checks plus a closed set of computational adapters.

These checks do not certify arbitrary natural language or third-party code.
The lab supplies no synthesis, wet-lab, hardware-control or arbitrary-code tool.
"""
from __future__ import annotations

import re


class ResearchSafetyError(ValueError):
    pass


def check_research_purpose(text):
    if not isinstance(text, str) or len(text) > 20000:
        raise ValueError("Research purpose must be bounded text.")
    normalized = " ".join(text.casefold().split())
    biological = r"(?:pathogenicity|virulence|transmissibility|immune evasion|host range|drug resistance)"
    harmful = (re.search(r"(?:increase|enhance|maximize|optimise|optimize|improve).{0,100}" + biological, normalized)
               or re.search(biological + r".{0,100}(?:increase|enhance|maximi[sz]e|optimi[sz]e)", normalized))
    operational = re.search(r"(?:make|synthesize|manufacture|mix|produce|recipe|protocol|procedure).{0,90}(?:explosive|poison|toxic gas|nerve agent|chlorine gas|pathogen)", normalized)
    if harmful or operational:
        raise ResearchSafetyError("This laboratory cannot optimize harmful biological capability or supply hazardous preparation instructions. Safe prevention, hazard review and beneficial public-data analysis remain available.")
    return {"classification": "COMPUTATIONAL_ONLY", "physical_authorization": False,
            "limitation": "Only bounded registered models are executable; no physical or wet-lab validation."}
