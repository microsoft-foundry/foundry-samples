"""
AI Gateway Integration Module

Demonstrates Azure API Management integration for centralized agent access control.
"""

import os
import helpers

class GatewayIntegration:
    """Handles API Management gateway configuration."""
    
    def __init__(self, project_client, agent_id: str):
        self.project_client = project_client
        self.agent_id = agent_id
        self.apim_endpoint = os.getenv("APIM_ENDPOINT", "https://your-apim.azure-api.net")
    
    # <apim_policies>
    # NOTE: This code is a non-runnable snippet of the larger sample code from which it is taken.
    def configure_gateway_policies(self):
        """Configure API Management policies."""
        helpers.print_info("Configuring API Management policies...")
        
        config = {
            "configuration": {
                "endpoint": f"{self.apim_endpoint}/agents/workplace",
                "rate_limit": "100 requests per minute per user",
                "caching_enabled": True,
                "analytics_enabled": True
            },
            "policies": [
                "Rate limiting per subscription",
                "Request/response transformation",
                "OAuth 2.0 authentication",
                "CORS configuration",
                "Response caching (5 minutes)"
            ]
        }
        
        # Generate XML policy file
        policy_xml = """<policies>
    <inbound>
        <rate-limit-by-key calls="100" renewal-period="60" counter-key="@(context.Subscription.Id)" />
        <cors><allowed-origins><origin>*</origin></allowed-origins></cors>
        <cache-lookup vary-by-developer="false" vary-by-developer-groups="false" />
    </inbound>
    <backend><forward-request /></backend>
    <outbound>
        <cache-store duration="300" />
    </outbound>
</policies>"""
        
        with open("gateway_policies.xml", "w") as f:
            f.write(policy_xml)
        
        return config
    # </apim_policies>
    
    def run(self):
        """Execute gateway integration."""
        helpers.print_header("AI Gateway Integration")
        
        config = self.configure_gateway_policies()
        helpers.print_gateway_summary(config)
        helpers.save_json(config, "gateway_config.json")
        
        return config

def main():
    """Standalone execution."""
    from dotenv import load_dotenv
    load_dotenv()
    
    class MockProjectClient:
        pass
    
    gateway = GatewayIntegration(MockProjectClient(), os.getenv("AGENT_ID", "agent-test"))
    gateway.run()

if __name__ == "__main__":
    main()
