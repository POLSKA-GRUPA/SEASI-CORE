"""SEASI-CORE: neutral multi-tenant kernel for governed agentic workflows.

The kernel is intentionally small. It owns:

- versioned, closed contracts (tenancy, capabilities, events, evidence, workflows);
- a fail-closed execution model (no implicit tenant, no implicit effects);
- a neutral runner with Human-in-the-Loop approval authority;
- registries and policies that external modules plug into.

Domain logic (accounting, fiscal, marketing, ...) NEVER lives here.
"""

__version__ = "0.1.0"
