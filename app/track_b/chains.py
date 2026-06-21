from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field


class QueryFilters(BaseModel):
    type: str | None = Field(
        None,
        description=(
            "Filter by asset type: domain, subdomain, ip_address, "
            "service, certificate, technology"
        ),
    )
    status: str | None = Field(
        None, description="Filter by status: active, stale, archived"
    )
    tag: str | None = Field(None, description="Filter by tag label")
    search: str | None = Field(
        None, description="Search string to match against asset value"
    )
    expired: bool | None = Field(
        None, description="Set to true to find expired certificates"
    )
    explanation: str = Field(
        description=(
            "Brief explanation of what the query is looking for in plain English"
        )
    )


_QUERY_SYSTEM = (
    "You are an asset query translator. Given a natural language question about "
    "internet-facing assets, extract structured filter criteria.\n"
    "\n"
    "Available asset types: domain, subdomain, ip_address, service, "
    "certificate, technology\n"
    "Available statuses: active, stale, archived\n"
    "Assets have tags (free-form labels) for grouping.\n"
    "Certificate expiry dates are stored in metadata under the key 'expires'."
)

query_prompt = ChatPromptTemplate.from_messages(
    [("system", _QUERY_SYSTEM), ("human", "{question}")]
)


class RiskFinding(BaseModel):
    severity: str = Field(description="low, medium, high, or critical")
    detail: str = Field(description="Description of the finding")
    asset_value: str = Field(description="The asset value this finding relates to")


class RiskAssessment(BaseModel):
    overall_score: int = Field(ge=0, le=10, description="Overall risk score 0-10")
    summary: str = Field(description="One-paragraph risk summary")
    findings: list[RiskFinding] = Field(description="Specific risk findings")
    recommendations: list[str] = Field(description="Recommended actions")


_RISK_SYSTEM = (
    "You are a security risk assessor. Analyze the provided asset data "
    "and produce a risk assessment.\n"
    "\n"
    "Consider:\n"
    "- Expired or expiring certificates\n"
    "- Exposed services on unusual or sensitive ports\n"
    "- End-of-life or outdated technologies and versions\n"
    "- Sensitive data exposure in metadata or tags\n"
    "- Services with no encryption or authentication indicators\n"
    "- Stale assets that may indicate forgotten infrastructure\n"
    "\n"
    "Score 0-10 where 0 is no risk and 10 is critical risk."
)

risk_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", _RISK_SYSTEM),
        ("human", "Assess the risk for these assets:\n\n{assets}"),
    ]
)


class EnrichmentResult(BaseModel):
    environment: str = Field(
        description=("Environment classification: prod, staging, dev, or unknown")
    )
    category: str = Field(description="Functional category of this asset")
    criticality: str = Field(
        description="Business criticality: critical, high, medium, low"
    )
    rationale: str = Field(description="Why these classifications were chosen")


_ENRICH_SYSTEM = (
    "You are an asset enrichment specialist. Given raw asset data, "
    "classify and enrich it.\n"
    "\n"
    "Determine:\n"
    "1. Environment: is this asset likely prod, staging, dev, or unknown? "
    "Look at tags, value patterns (api vs dev-api vs staging-api), "
    "and metadata.\n"
    "2. Category: what function does this asset serve? "
    "(e.g., API endpoint, DNS resolver, web server, database, CDN, "
    "monitoring, authentication)\n"
    "3. Criticality: how business-critical is this asset? "
    "Consider whether it handles auth, payments, PII, "
    "or is customer-facing.\n"
    "\n"
    "Provide clear rationale for each classification."
)

enrich_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", _ENRICH_SYSTEM),
        ("human", "Classify and enrich this asset:\n\n{asset_data}"),
    ]
)

_REPORT_SYSTEM = (
    "You are a security report writer. Given a collection of assets, "
    "generate a clear, readable inventory and risk report.\n"
    "\n"
    "Structure the report with:\n"
    "1. **Executive Summary** - brief overview of what was found\n"
    "2. **Inventory Summary** - counts by type, notable assets\n"
    "3. **Risk Findings** - key security concerns identified\n"
    "4. **Recommendations** - prioritized actions\n"
    "\n"
    "Be specific and reference actual asset values. "
    "Do not invent assets that are not in the data."
)

report_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", _REPORT_SYSTEM),
        ("human", "Generate a report for these assets:\n\n{assets}"),
    ]
)
