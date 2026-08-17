# Provenance

SEASI-CORE was founded as a clean-room kernel on 2026-08-16. It is a
from-scratch implementation: no file in this repository was copied from a
prior codebase.

What preceded it: the design lessons come from an internal precursor
platform operated privately by the author for professional-services
automation (document intake, filings, approval workflows). That precursor
remains outside this repository; its history is preserved privately and is
available for inspection under NDA during due diligence.

Why a clean room: the precursor mixed tenant-specific configuration,
brand-specific assumptions and kernel logic. SEASI-CORE extracts only the
architectural invariants — fail-closed tenancy, sealed approval intents
bound to a payload digest, deterministic neutral runner — as new code with
tests written alongside.

The product modules (GESTIÓN AUTÓNOMA, CONTA-LABORAL, MARKETING) live in
separate private repositories. Where those modules adapted code from the
precursor, each repository carries its own `docs/ip/PROVENANCE.csv` with a
per-file origin trace.

Authorship: all commits are by Kenyi Martín Alcántara. Intellectual
property assignment to the investable entity is documented separately in
the data room (see `docs/ip/` in the module repositories).
