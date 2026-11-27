# Copyright (c) Microsoft. All rights reserved.

"""A read-only MCP server with fictional support cases and knowledge articles."""

from mcp.server.mcpserver import MCPServer

server = MCPServer("fictional-support")

CASES = {
    "BILL-1042": {
        "case_id": "BILL-1042",
        "category": "billing",
        "summary": (
            "The customer reduced their subscription from 12 seats to 8 seats "
            "during the current billing term, but the invoice still lists 12 seats."
        ),
        "article_id": "BILL-RENEWAL",
    },
    "TECH-2048": {
        "case_id": "TECH-2048",
        "category": "technical",
        "summary": (
            "Users cannot sign in with SSO after the identity provider's "
            "signing certificate expired."
        ),
        "article_id": "TECH-SSO-CERT",
    },
}

ARTICLES = {
    "BILL-RENEWAL": {
        "article_id": "BILL-RENEWAL",
        "title": "Seat reductions and renewals",
        "guidance": (
            "Seat reductions take effect at the next renewal. The current "
            "billing term is not prorated. Confirm the renewal date with the "
            "customer before advising when the 8-seat price will apply."
        ),
    },
    "TECH-SSO-CERT": {
        "article_id": "TECH-SSO-CERT",
        "title": "Expired SSO signing certificate",
        "guidance": (
            "Renew the identity provider's signing certificate, update the "
            "SaaS application's SSO metadata, and test sign-in with a "
            "non-admin account. Escalate if sign-in still fails."
        ),
    },
}


@server.tool()
def lookup_case(case_id: str) -> dict:
    """Find a fictional support case by its case ID."""
    normalized_id = case_id.strip().upper()
    case = CASES.get(normalized_id)
    if case is None:
        return {"found": False, "case_id": normalized_id}
    return {"found": True, **case}


@server.tool()
def get_knowledge_article(article_id: str) -> dict:
    """Find a fictional knowledge article by the ID returned with a case."""
    normalized_id = article_id.strip().upper()
    article = ARTICLES.get(normalized_id)
    if article is None:
        return {"found": False, "article_id": normalized_id}
    return {"found": True, **article}


if __name__ == "__main__":
    server.run(transport="stdio")
