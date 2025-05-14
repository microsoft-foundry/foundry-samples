"""
Azure Logic Apps integration for AI agents.
This module provides utilities to connect AI agents with Azure Logic Apps triggers.
"""

import json
import requests
from typing import Dict, Any, Callable, List, Optional
from azure.identity import DefaultAzureCredential
from azure.core.credentials import AccessToken
from datetime import datetime, timezone, timedelta

class AzureLogicAppTool:
    """
    A tool for interacting with Azure Logic Apps from AI agents.
    This class provides methods to register and trigger Logic App workflows.
    """
    
    def __init__(self, subscription_id: str, resource_group: str):
        """
        Initialize the AzureLogicAppTool.
        
        Args:
            subscription_id (str): Azure subscription ID
            resource_group (str): Azure resource group containing the Logic App
        """
        self.subscription_id = subscription_id
        self.resource_group = resource_group
        self.credential = DefaultAzureCredential()
        self._token: Optional[AccessToken] = None
        self._token_expires_on: Optional[datetime] = None
        self.registered_apps: Dict[str, Dict[str, str]] = {}
        
    def _ensure_token(self) -> str:
        """
        Ensure a valid access token is available.
        
        Returns:
            str: A valid Azure access token
        """
        now = datetime.now(timezone.utc)
        
        # If token doesn't exist or is about to expire (within 5 minutes), refresh it
        if (not self._token or not self._token_expires_on or now + timedelta(minutes=5) >= self._token_expires_on):
            self._token = self.credential.get_token("https://management.azure.com/.default")
            self._token_expires_on = datetime.fromtimestamp(self._token.expires_on, timezone.utc)
            
        return self._token.token
    
    def register_logic_app(self, logic_app_name: str, trigger_name: str) -> None:
        """
        Register a Logic App and its trigger for use.
        
        Args:
            logic_app_name (str): Name of the Logic App
            trigger_name (str): Name of the trigger to use
        """
        self.registered_apps[logic_app_name] = {
            "app_name": logic_app_name,
            "trigger_name": trigger_name
        }
        
    def trigger_logic_app(self, logic_app_name: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Trigger a Logic App workflow and return the result.
        
        Args:
            logic_app_name (str): Name of the registered Logic App to trigger
            params (Dict[str, Any], optional): Parameters to pass to the Logic App

        Returns:
            Dict[str, Any]: Response from the Logic App
        """
        if logic_app_name not in self.registered_apps:
            raise ValueError(f"Logic App '{logic_app_name}' not registered. Call register_logic_app first.")
        
        app_info = self.registered_apps[logic_app_name]
        token = self._ensure_token()
        
        # Construct the Logic App trigger URL
        trigger_url = (
            f"https://management.azure.com/subscriptions/{self.subscription_id}/"
            f"resourceGroups/{self.resource_group}/providers/Microsoft.Logic/"
            f"workflows/{app_info['app_name']}/triggers/{app_info['trigger_name']}/"
            f"run?api-version=2016-06-01"
        )
        
        # Prepare headers with authentication
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        # Make the request to trigger the Logic App
        response = requests.post(
            trigger_url,
            headers=headers,
            json=params or {}
        )
        
        # Check if the request was successful
        response.raise_for_status()
        
        # For synchronous Logic Apps, we may get an immediate response
        if response.text:
            try:
                return response.json()
            except json.JSONDecodeError:
                return {"message": "Logic App triggered successfully, but response was not JSON"}
        
        return {"message": "Logic App triggered successfully"}

_logic_app_tool_singleton: Optional[AzureLogicAppTool] = None

def init_logic_app_tool_singleton(subscription_id: str, resource_group: str):
    """
    Initialize the singleton instance with subscription_id and resource_group.
    Call this once before using get_logic_app_tool_singleton().
    """
    global _logic_app_tool_singleton
    _logic_app_tool_singleton = AzureLogicAppTool(subscription_id, resource_group)

def get_logic_app_tool_singleton() -> AzureLogicAppTool:
    """
    Get the singleton instance. Must call init_logic_app_tool_singleton first.
    """
    global _logic_app_tool_singleton
    if _logic_app_tool_singleton is None:
        raise RuntimeError("LogicAppTool singleton not initialized. Call init_logic_app_tool_singleton first.")
    return _logic_app_tool_singleton

def register_logic_app_singleton(logic_app_name: str, trigger_name: str):
    """
    Register a Logic App and its trigger using the singleton.
    """
    get_logic_app_tool_singleton().register_logic_app(logic_app_name, trigger_name)

def create_event_details_function(logic_app_name: str) -> Callable:
    """
    Create a function to retrieve event details from Logic App.
    (DEPRECATED: Use the top-level fetch_event_details instead for agent integration.)
    """
    def _fetch_event_details_closure(
        email: str = None,
        start_date: str = None, 
        end_date: str = None,
        event_id: str = None,
        include_attendees: bool = True
    ) -> str:
        """
        Fetch event or meeting details from Microsoft Graph via Logic App.
        
        Args:
            email (str, optional): The email address of the user whose events are to be retrieved.
            start_date (str, optional): Start of the date range to filter events (ISO 8601 format, e.g., '2025-05-01T00:00:00Z').
            end_date (str, optional): End of the date range to filter events (ISO 8601 format, e.g., '2025-05-02T00:00:00Z').
            event_id (str, optional): Specific event ID to retrieve (optional).
            include_attendees (bool, optional): Whether to include attendee details in the response (default: True).
            
        Returns:
            str: JSON string with event details or error message.
        """
        payload = {}
        if email:
            payload["userEmail"] = email
        if start_date:
            payload["startDate"] = start_date
        if end_date:
            payload["endDate"] = end_date
        if event_id:
            payload["eventId"] = event_id
        payload["includeAttendees"] = include_attendees
        
        try:
            # Call the Logic App and return the result
            result = get_logic_app_tool_singleton().trigger_logic_app(logic_app_name, payload)
            return json.dumps(result)
        except Exception as e:
            return json.dumps({
                "error": str(e),
                "message": "Failed to retrieve event details"
            })
    
    _fetch_event_details_closure.__name__ = "_fetch_event_details_closure"
    return _fetch_event_details_closure


def fetch_event_details(
    logic_app_name: str,
    email: str = None,
    start_date: str = None,
    end_date: str = None,
    event_id: str = None,
    include_attendees: bool = True
) -> str:
    """
    Fetch event or meeting details from Microsoft Graph via Logic App.
    Args:
        logic_app_name (str): Name of the registered Logic App to use
        email (str, optional): The email address of the user whose events are to be retrieved.
        start_date (str, optional): Start of the date range to filter events (ISO 8601 format, e.g., '2025-05-01T00:00:00Z').
        end_date (str, optional): End of the date range to filter events (ISO 8601 format, e.g., '2025-05-02T00:00:00Z').
        event_id (str, optional): Specific event ID to retrieve (optional).
        include_attendees (bool, optional): Whether to include attendee details in the response (default: True).
        
    Returns:
        str: JSON string with event details or error message.
    """
    payload = {}
    if email:
        payload["userEmail"] = email
    if start_date:
        payload["startDate"] = start_date
    if end_date:
        payload["endDate"] = end_date
    if event_id:
        payload["eventId"] = event_id
    payload["includeAttendees"] = include_attendees
    
    try:
        result = get_logic_app_tool_singleton().trigger_logic_app(logic_app_name, payload)
        return json.dumps(result)
    except Exception as e:
        return json.dumps({
            "error": str(e),
            "message": "Failed to retrieve event details"
        })