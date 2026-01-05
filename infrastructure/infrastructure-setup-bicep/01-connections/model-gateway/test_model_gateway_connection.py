#!/usr/bin/env python3
"""
Modular ModelGateway Connection Validator

This script validates ModelGateway connections by breaking down validation into modular components:
1. Parameter validation (static vs dynamic, structure validation)
2. Dynamic discovery validation (API calls)
3. Model validation (static list or dynamic lookup)
4. Chat completions validation (end-to-end test)

Usage:
    python validate_model_gateway_modular.py --params <parameter-file> --api-key <key> --deployment-name <name> [--client-secret <secret>]
"""

import argparse
import json
import sys
import time
import requests
from typing import Dict, Any, Optional, Tuple, List
from enum import Enum
from dataclasses import dataclass

# Color constants for terminal output
class Colors:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    NC = '\033[0m'  # No Color

class AuthType(Enum):
    API_KEY = "apikey"
    OAUTH2 = "oauth2"

class ModelDiscoveryType(Enum):
    STATIC = "static"
    DYNAMIC = "dynamic"
    NONE = "none"

@dataclass
class ValidationConfig:
    # Basic configuration
    target_url: str
    gateway_name: str
    auth_type: AuthType
    deployment_in_path: bool
    inference_api_version: str
    deployment_name: str
    
    # Authentication
    api_key: Optional[str]
    client_secret: Optional[str]
    auth_config: Optional[Dict[str, Any]]
    custom_headers: Optional[Dict[str, str]]
    
    # OAuth2
    client_id: Optional[str]
    token_url: Optional[str]
    scopes: Optional[List[str]]
    
    # Model Discovery
    static_models: Optional[List[Dict[str, Any]]]
    list_models_endpoint: Optional[str]
    get_model_endpoint: Optional[str]
    deployment_provider: Optional[str]
    deployment_api_version: str

class ModelGatewayValidator:
    """Main validator class for ModelGateway connections"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.timeout = 30
    
    def print_colored(self, text: str, color: str = Colors.NC) -> None:
        """Print text with color"""
        print(f"{color}{text}{Colors.NC}")
    
    def load_parameter_file(self, file_path: str) -> Dict[str, Any]:
        """Load and parse Bicep parameter file"""
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
            return data.get('parameters', {})
        except FileNotFoundError:
            self.print_colored(f"❌ Error: Parameter file not found: {file_path}", Colors.RED)
            sys.exit(1)
        except json.JSONDecodeError as e:
            self.print_colored(f"❌ Error: Invalid JSON in parameter file: {e}", Colors.RED)
            sys.exit(1)
    
    def extract_parameter_value(self, param: Dict[str, Any]) -> Any:
        """Extract value from Bicep parameter format"""
        if isinstance(param, dict) and 'value' in param:
            return param['value']
        return param
    
    def parse_config_from_params(self, params: Dict[str, Any], api_key: str, 
                                client_secret: str, deployment_name: str) -> ValidationConfig:
        """Parse configuration from Bicep parameters"""
        
        # Convert deployment_in_path string to boolean if needed
        deployment_in_path = self.extract_parameter_value(params.get('deploymentInPath', {}))
        if isinstance(deployment_in_path, str):
            deployment_in_path = deployment_in_path.lower() == 'true'
        
        # Parse auth type
        auth_type_str = self.extract_parameter_value(params.get('authType', {}))
        try:
            auth_type = AuthType(auth_type_str.lower() if auth_type_str else "apikey")
        except ValueError:
            auth_type = AuthType.API_KEY
        
        return ValidationConfig(
            target_url=self.extract_parameter_value(params.get('targetUrl', {})),
            gateway_name=self.extract_parameter_value(params.get('gatewayName', {})),
            auth_type=auth_type,
            deployment_in_path=deployment_in_path,
            inference_api_version=self.extract_parameter_value(params.get('inferenceAPIVersion', {})) or "",
            deployment_name=deployment_name,
            
            # Authentication
            api_key=api_key,
            client_secret=client_secret,
            auth_config=self.extract_parameter_value(params.get('authConfig', {})),
            custom_headers=self.extract_parameter_value(params.get('customHeaders', {})),
            
            # OAuth2
            client_id=self.extract_parameter_value(params.get('clientId', {})),
            token_url=self.extract_parameter_value(params.get('tokenUrl', {})),
            scopes=self.extract_parameter_value(params.get('scopes', {})),
            
            # Model Discovery
            static_models=self.extract_parameter_value(params.get('staticModels', {})),
            list_models_endpoint=self.extract_parameter_value(params.get('listModelsEndpoint', {})),
            get_model_endpoint=self.extract_parameter_value(params.get('getModelEndpoint', {})),
            deployment_provider=self.extract_parameter_value(params.get('deploymentProvider', {})),
            deployment_api_version=self.extract_parameter_value(params.get('deploymentAPIVersion', {})) or ""
        )

    # ============================================================================
    # 1. PARAMETER VALIDATION MODULE
    # ============================================================================
    
    def validate_params(self, config: ValidationConfig) -> bool:
        """
        Validate all parameter configuration
        Returns: True if all validations pass, False otherwise
        """
        self.print_colored("📋 Step 1: Parameter Validation", Colors.BLUE)
        print("=" * 50)
        
        # 1a. Basic config validation
        if not self._validate_basic_config(config):
            return False
            
        # 1b. Exactly one of static or dynamic
        if not self._validate_discovery_method_exclusivity(config):
            return False
            
        # 1c. Validate static structure if configured
        if not self._validate_static_structure(config):
            return False
            
        # 1d. Validate dynamic structure if configured
        if not self._validate_dynamic_structure(config):
            return False
            
        # 1e. Validate OAuth2 if configured
        if not self._validate_oauth2_structure(config):
            return False
        
        self.print_colored("✅ Parameter validation passed", Colors.GREEN)
        print()
        return True
    
    def _validate_basic_config(self, config: ValidationConfig) -> bool:
        """Validate basic configuration requirements"""
        self.print_colored("🔍 1a. Basic Configuration Check:", Colors.YELLOW)
        
        if not config.target_url:
            self.print_colored("❌ Error: targetUrl is required in parameter file", Colors.RED)
            return False
        print("✅ Target URL configured")
        
        if not config.deployment_name:
            self.print_colored("❌ Error: deployment name is required (use --deployment-name)", Colors.RED)
            return False
        print("✅ Deployment name provided")
        
        print("✅ Basic configuration valid")
        return True
    
    def _validate_discovery_method_exclusivity(self, config: ValidationConfig) -> bool:
        """Validate exactly one discovery method is configured"""
        self.print_colored("🔍 1b. Model Discovery Method Check:", Colors.YELLOW)
        
        has_static = config.static_models and len(config.static_models) > 0
        has_dynamic = (config.list_models_endpoint and 
                      config.get_model_endpoint and 
                      config.deployment_provider)
        has_partial_dynamic = bool(config.list_models_endpoint or 
                                  config.get_model_endpoint or 
                                  config.deployment_provider)
        
        if has_static and has_dynamic:
            self.print_colored("❌ Error: Both static models and dynamic discovery configured", Colors.RED)
            self.print_colored("You must configure exactly one model discovery method, not both.", Colors.NC)
            print()
            self.print_colored("📋 Fix in your Bicep parameter file:", Colors.BLUE)
            print("Choose one of these approaches:")
            print("1. Use static models: Keep 'staticModels' and remove dynamic discovery parameters")
            print("   - Remove: listModelsEndpoint, getModelEndpoint, deploymentProvider")
            print("2. Use dynamic discovery: Remove 'staticModels' and keep dynamic parameters")
            print("   - Keep: listModelsEndpoint, getModelEndpoint, deploymentProvider")
            return False
        
        elif has_partial_dynamic and not has_dynamic:
            self.print_colored("❌ Error: Incomplete dynamic discovery configuration", Colors.RED)
            self.print_colored("All three parameters are required for dynamic discovery.", Colors.NC)
            print()
            self.print_colored("📋 Missing or incomplete parameters in your Bicep file:", Colors.BLUE)
            if not config.list_models_endpoint:
                print("❌ listModelsEndpoint: Required (e.g., \"/deployments\")")
            else:
                print("✅ listModelsEndpoint: Configured")
            
            if not config.get_model_endpoint:
                print("❌ getModelEndpoint: Required (e.g., \"/deployments/{deploymentName}\")")
            else:
                print("✅ getModelEndpoint: Configured")
            
            if not config.deployment_provider:
                print("❌ deploymentProvider: Required (\"AzureOpenAI\" or \"OpenAI\")")
            else:
                print("✅ deploymentProvider: Configured")
            return False
        
        elif not has_static and not has_dynamic and not has_partial_dynamic:
            self.print_colored("❌ Error: No model discovery configuration found", Colors.RED)
            self.print_colored("Your parameter file must configure exactly one model discovery method.", Colors.NC)
            print()
            self.print_colored("📋 Fix in your Bicep parameter file:", Colors.BLUE)
            print("Choose one of these approaches:")
            print("1. Static models: Add 'staticModels' array with your model deployments")
            print("2. Dynamic discovery: Add all three required parameters:")
            print("   - listModelsEndpoint: \"/deployments\"")
            print("   - getModelEndpoint: \"/deployments/{deploymentName}\"")
            print("   - deploymentProvider: \"AzureOpenAI\" or \"OpenAI\"")
            return False
        
        if has_static:
            print("✅ Using static model discovery")
        else:
            print("✅ Using dynamic model discovery")
        
        return True
    
    def _validate_static_structure(self, config: ValidationConfig) -> bool:
        """Validate static model configuration structure"""
        if not config.static_models:
            return True  # No static models configured
            
        self.print_colored("🔍 1c. Static Model Structure Check:", Colors.YELLOW)
        
        if not isinstance(config.static_models, list):
            self.print_colored("❌ Error: staticModels must be an array", Colors.RED)
            return False
        
        for i, model in enumerate(config.static_models):
            if not isinstance(model, dict):
                self.print_colored(f"❌ Error: staticModels[{i}] must be an object", Colors.RED)
                return False
                
            if not model.get('name'):
                self.print_colored(f"❌ Error: staticModels[{i}] missing 'name' field", Colors.RED)
                return False
                
            properties = model.get('properties', {})
            if not isinstance(properties, dict):
                self.print_colored(f"❌ Error: staticModels[{i}].properties must be an object", Colors.RED)
                return False
                
            model_info = properties.get('model', {})
            if not isinstance(model_info, dict):
                self.print_colored(f"❌ Error: staticModels[{i}].properties.model must be an object", Colors.RED)
                return False
                
            if not model_info.get('name'):
                self.print_colored(f"❌ Error: staticModels[{i}].properties.model missing 'name' field", Colors.RED)
                return False
                
            if not model_info.get('format'):
                self.print_colored(f"⚠️  Warning: staticModels[{i}].properties.model missing 'format' field", Colors.YELLOW)
        
        print(f"✅ Static model structure valid ({len(config.static_models)} models)")
        return True
    
    def _validate_dynamic_structure(self, config: ValidationConfig) -> bool:
        """Validate dynamic discovery configuration structure"""
        has_dynamic = (config.list_models_endpoint and 
                      config.get_model_endpoint and 
                      config.deployment_provider)
        
        if not has_dynamic:
            return True  # No dynamic discovery configured
            
        self.print_colored("🔍 1d. Dynamic Discovery Structure Check:", Colors.YELLOW)
        
        # Validate deploymentProvider value
        valid_providers = ["AzureOpenAI", "OpenAI"]
        if config.deployment_provider not in valid_providers:
            self.print_colored("❌ Error: Invalid deploymentProvider value", Colors.RED)
            self.print_colored(f"Current value: {config.deployment_provider}", Colors.NC)
            print()
            self.print_colored("📋 Fix in your Bicep parameter file:", Colors.BLUE)
            print("Set deploymentProvider to one of these exact values:")
            for provider in valid_providers:
                print(f"  - \"{provider}\"")
            return False
        
        # Validate getModelEndpoint template
        if "{deploymentName}" not in config.get_model_endpoint:
            self.print_colored("❌ Error: getModelEndpoint must contain '{deploymentName}' template", Colors.RED)
            self.print_colored(f"Current value: {config.get_model_endpoint}", Colors.NC)
            print()
            self.print_colored("📋 Fix in your Bicep parameter file:", Colors.BLUE)
            print("Update getModelEndpoint to include the {deploymentName} placeholder:")
            print("Example: \"/deployments/{deploymentName}\" or \"/models/{deploymentName}\"")
            return False
        
        print("✅ Dynamic discovery structure valid")
        return True
    
    def _validate_oauth2_structure(self, config: ValidationConfig) -> bool:
        """Validate OAuth2 configuration structure"""
        if config.auth_type != AuthType.OAUTH2:
            return True  # Not using OAuth2
            
        self.print_colored("🔍 1e. OAuth2 Configuration Check:", Colors.YELLOW)
        
        if not all([config.client_id, config.token_url, config.client_secret]):
            self.print_colored("❌ Error: OAuth2 requires clientId, tokenUrl, and clientSecret", Colors.RED)
            print()
            self.print_colored("📋 Required parameters in your Bicep file:", Colors.BLUE)
            print("- clientId: Your OAuth2 client identifier")
            print("- tokenUrl: Your OAuth2 token endpoint URL")
            print("- clientSecret: Provided via --client-secret parameter")
            return False
        
        print("✅ OAuth2 configuration valid")
        return True

    # ============================================================================
    # 2. DYNAMIC DISCOVERY VALIDATION MODULE
    # ============================================================================
    
    def validate_dynamic_discovery(self, config: ValidationConfig, headers: Dict[str, str]) -> bool:
        """
        Validate dynamic model discovery endpoints with API calls
        Returns: True if dynamic discovery is working, False otherwise
        """
        has_dynamic = (config.list_models_endpoint and 
                      config.get_model_endpoint and 
                      config.deployment_provider)
        
        if not has_dynamic:
            return True  # Skip if not using dynamic discovery
            
        self.print_colored("📋 Step 2: Dynamic Discovery Validation", Colors.BLUE)
        print("=" * 50)
        
        base_url = config.target_url.rstrip('/')
        
        # Test list models endpoint
        if not self._test_list_models_endpoint(config, headers, base_url):
            return False
            
        # Test get model endpoint
        if not self._test_get_model_endpoint(config, headers, base_url):
            return False
        
        self.print_colored("✅ Dynamic discovery validation passed", Colors.GREEN)
        print()
        return True
    
    def _test_list_models_endpoint(self, config: ValidationConfig, headers: Dict[str, str], base_url: str) -> bool:
        """Test the list models endpoint"""
        self.print_colored("🔍 2a. List Models Endpoint Test:", Colors.YELLOW)
        
        list_url = f"{base_url}{config.list_models_endpoint}"
        if config.deployment_api_version:
            list_url += f"?api-version={config.deployment_api_version}"
        
        print(f"Testing: {list_url}")
        
        # Show curl command for list models
        self.print_colored("📋 Curl command for list models:", Colors.BLUE)
        list_curl = self._generate_get_curl(list_url, headers)
        print(list_curl)
        print()
        
        try:
            response = self.session.get(list_url, headers=headers)
            
            if response.status_code == 401:
                self._handle_discovery_401_error(config)
                return False
            elif response.status_code != 200:
                self.print_colored(f"❌ List models endpoint failed: {response.status_code}", Colors.RED)
                try:
                    error_details = response.json()
                    print(f"Error: {error_details}")
                except:
                    print(f"Response: {response.text[:200]}")
                return False
            
            self.print_colored("✅ List models endpoint working", Colors.GREEN)
            
            # Parse response based on deployment provider
            try:
                response_data = response.json()
                models = []
                
                if config.deployment_provider.lower() == "azureopenai":
                    models = response_data.get('value', [])
                elif config.deployment_provider.lower() == "openai":
                    models = response_data.get('data', [])
                
                if models:
                    print(f"Found {len(models)} models:")
                    for model in models[:5]:  # Show first 5
                        if config.deployment_provider.lower() == "azureopenai":
                            name = model.get('name', 'Unknown')
                        else:
                            name = model.get('id', 'Unknown')
                        print(f"   - {name}")
                    
                    if len(models) > 5:
                        print(f"   ... and {len(models) - 5} more")
                else:
                    self.print_colored("❌ Error: No models found in list response", Colors.RED)
                    self.print_colored("📋 Actual Response:", Colors.YELLOW)
                    print(f"   {json.dumps(response_data, indent=2)[:500]}{'...' if len(str(response_data)) > 500 else ''}")
                    self.print_colored("⚠️ Response not in expected format for dynamic discovery", Colors.YELLOW)
                    return False
            
            except json.JSONDecodeError:
                self.print_colored("⚠️  List models response is not valid JSON", Colors.YELLOW)
        
        except requests.exceptions.RequestException as e:
            self.print_colored(f"❌ List models endpoint error: {str(e)}", Colors.RED)
            return False
        
        return True
    
    def _test_get_model_endpoint(self, config: ValidationConfig, headers: Dict[str, str], base_url: str) -> bool:
        """Test the get model endpoint"""
        self.print_colored("🔍 2b. Get Model Endpoint Test:", Colors.YELLOW)
        
        if "{deploymentName}" not in config.get_model_endpoint:
            self.print_colored("❌ Error: getModelEndpoint missing {deploymentName} template", Colors.RED)
            return False
        
        get_url = f"{base_url}{config.get_model_endpoint.replace('{deploymentName}', config.deployment_name)}"
        if config.deployment_api_version:
            get_url += f"?api-version={config.deployment_api_version}"
        
        print(f"Testing: {get_url}")
        
        # Show curl command for get model
        self.print_colored("📋 Curl command for get model:", Colors.BLUE)
        get_curl = self._generate_get_curl(get_url, headers)
        print(get_curl)
        print()
        
        try:
            response = self.session.get(get_url, headers=headers)
            
            if response.status_code == 401:
                self._handle_discovery_401_error(config)
                return False
            elif response.status_code != 200:
                self.print_colored(f"❌ Get model endpoint failed: {response.status_code}", Colors.RED)
                print("The get model endpoint is not working correctly")
                try:
                    error_details = response.json()
                    print(f"Error: {error_details}")
                except:
                    print(f"Response: {response.text[:200]}")
                return False
            
            self.print_colored("✅ Get model endpoint working", Colors.GREEN)
            
            try:
                model_data = response.json()
                
                if config.deployment_provider.lower() == "azureopenai":
                    if 'properties' in model_data and 'model' in model_data.get('properties', {}):
                        model_info = model_data['properties']['model']
                        model_name = model_info.get('name', 'Unknown')
                        model_version = model_info.get('version', '')
                        model_format = model_info.get('format', '')
                        
                        print(f"   Model details: {model_name}")
                        print(f"   Model version: {model_version}")
                        print(f"   Model format: {model_format}")
                        
                        if not model_name or model_name == 'Unknown':
                            self.print_colored("❌ Error: Model name not found in Azure OpenAI response", Colors.RED)
                            return False
                        if not model_format:
                            self.print_colored("❌ Error: Model format not specified in Azure OpenAI response", Colors.RED)
                            return False
                    else:
                        self.print_colored("❌ Error: Response format doesn't match Azure OpenAI expected structure", Colors.RED)
                        self.print_colored("📋 Actual Response:", Colors.YELLOW)
                        print(f"   {json.dumps(model_data, indent=2)[:500]}{'...' if len(str(model_data)) > 500 else ''}")
                        self.print_colored("⚠️ Response not in expected Azure OpenAI format for dynamic discovery", Colors.YELLOW)
                        return False
                        
                else:  # OpenAI or other providers
                    if 'properties' in model_data and 'model' in model_data.get('properties', {}):
                        self.print_colored("❌ Error: Deployment provider mismatch detected!", Colors.RED)
                        self.print_colored("   Configuration says: OpenAI", Colors.RED)
                        self.print_colored("   Actual response format: Azure OpenAI", Colors.RED)
                        return False
                    
                    model_name = model_data.get('id', 'Unknown')
                    print(f"   Model details: {model_name}")
                    
                    if not model_name or model_name == 'Unknown':
                        self.print_colored("❌ Error: Model ID not found in OpenAI response", Colors.RED)
                        self.print_colored("📋 Actual Response:", Colors.YELLOW)
                        print(f"   {json.dumps(model_data, indent=2)[:500]}{'...' if len(str(model_data)) > 500 else ''}")
                        self.print_colored("⚠️ Response not in expected OpenAI format for dynamic discovery", Colors.YELLOW)
                        return False
            except json.JSONDecodeError:
                self.print_colored("⚠️  Warning: Get model endpoint response is not valid JSON", Colors.YELLOW)
            except Exception as e:
                self.print_colored(f"⚠️  Warning: Error parsing get model response: {str(e)}", Colors.YELLOW)
        
        except requests.exceptions.RequestException as e:
            self.print_colored(f"❌ Get model endpoint error: {str(e)}", Colors.RED)
            return False
        
        return True

    # ============================================================================
    # 3. MODEL VALIDATION MODULE
    # ============================================================================
    
    def validate_model(self, config: ValidationConfig) -> bool:
        """
        Validate that the specified deployment/model exists
        Returns: True if model validation passes, False otherwise
        """
        self.print_colored("📋 Step 3: Model Validation", Colors.BLUE)
        print("=" * 50)
        
        has_static = config.static_models and len(config.static_models) > 0
        
        if has_static:
            return self._validate_static_model_exists(config)
        else:
            # Dynamic validation already done in step 2
            self.print_colored("✅ Model validation passed (dynamic discovery already tested)", Colors.GREEN)
            print()
            return True
    
    def _validate_static_model_exists(self, config: ValidationConfig) -> bool:
        """Validate that deployment exists in static model list"""
        self.print_colored("🔍 3a. Static Model Existence Check:", Colors.YELLOW)
        
        deployment_found = False
        for model in config.static_models:
            if isinstance(model, dict) and model.get('name') == config.deployment_name:
                deployment_found = True
                self.print_colored(f"✅ Found deployment '{config.deployment_name}' in static models", Colors.GREEN)
                
                # Validate model properties
                properties = model.get('properties', {})
                model_info = properties.get('model', {})
                
                print(f"   - Model name: {model_info.get('name', 'Not specified')}")
                print(f"   - Model version: {model_info.get('version', 'Not specified')}")
                print(f"   - Model format: {model_info.get('format', 'Not specified')}")
                
                if not model_info.get('format'):
                    self.print_colored("⚠️  Warning: Model format not specified", Colors.YELLOW)
                
                break
        
        if not deployment_found:
            self.print_colored(f"❌ Deployment '{config.deployment_name}' not found in static models", Colors.RED)
            print("Available deployments in static models:")
            for model in config.static_models:
                if isinstance(model, dict):
                    print(f"   - {model.get('name', 'Unknown')}")
            print()
            self.print_colored("📋 Fix in your Bicep parameter file:", Colors.BLUE)
            print("- Add your deployment to the 'staticModels' array, or")
            print("- Use an existing deployment name from the list above")
            return False
        
        self.print_colored("✅ Model validation passed", Colors.GREEN)
        print()
        return True

    # ============================================================================
    # 4. CHAT COMPLETIONS VALIDATION MODULE
    # ============================================================================
    
    def validate_chat_completions(self, config: ValidationConfig, headers: Dict[str, str]) -> bool:
        """
        Validate chat completions endpoint with end-to-end test
        Returns: True if chat completions work, False otherwise
        """
        self.print_colored("📋 Step 4: Chat Completions Validation", Colors.BLUE)
        print("=" * 50)
        
        request_url = self._build_chat_completions_url(config)
        request_body = self._build_request_body(config)
        
        self.print_colored("🔗 Request Details:", Colors.YELLOW)
        print(f"Request URL: {request_url}")
        print(f"Deployment in path: {config.deployment_in_path}")
        print()
        
        # Show the curl command
        self.print_colored("📋 Curl command for chat completions:", Colors.BLUE)
        curl_command = self._generate_chat_curl(config, headers)
        print(curl_command)
        print()
        
        self.print_colored("🚀 Making test request...", Colors.BLUE)
        
        # Provide API version guidance
        if config.inference_api_version:
            self.print_colored(f"ℹ️  Using API version: {config.inference_api_version}", Colors.BLUE)
        print()
        
        try:
            start_time = time.time()
            response = self.session.post(request_url, headers=headers, json=request_body)
            end_time = time.time()
            
            response_time = f"{(end_time - start_time):.2f}s"
            
            self.print_colored("📊 Response Summary:", Colors.BLUE)
            print(f"HTTP Status: {response.status_code}")
            print(f"Response Time: {response_time}")
            print()
            
            if response.status_code == 200:
                return self._handle_chat_success_response(response)
            elif response.status_code == 404:
                return self._handle_chat_404_error(config)
            elif response.status_code == 401:
                return self._handle_chat_401_error(config)
            elif response.status_code == 400:
                return self._handle_chat_400_error(response)
            else:
                return self._handle_chat_other_error(response)
                
        except requests.exceptions.Timeout:
            self.print_colored("❌ Request timed out (30s)", Colors.RED)
            self.print_colored("🔧 Check if your gateway URL is accessible and responding", Colors.YELLOW)
            return False
        except requests.exceptions.ConnectionError:
            self.print_colored("❌ Connection error", Colors.RED)
            self.print_colored("🔧 Check if your gateway URL is correct and accessible", Colors.YELLOW)
            return False
        except Exception as e:
            self.print_colored(f"❌ Unexpected error: {str(e)}", Colors.RED)
            return False

    # ============================================================================
    # AUTHENTICATION AND UTILITY METHODS
    # ============================================================================
    
    def get_oauth_token(self, config: ValidationConfig) -> Optional[str]:
        """Get OAuth2 access token using client credentials flow"""
        if not all([config.client_id, config.token_url, config.client_secret]):
            return None
        
        try:
            token_data = {
                'grant_type': 'client_credentials',
                'client_id': config.client_id,
                'client_secret': config.client_secret
            }
            
            if config.scopes:
                token_data['scope'] = ' '.join(config.scopes)
            
            self.print_colored("🔐 Requesting OAuth2 token...", Colors.YELLOW)
            
            response = self.session.post(
                config.token_url,
                data=token_data,
                headers={'Content-Type': 'application/x-www-form-urlencoded'}
            )
            
            if response.status_code == 200:
                token_response = response.json()
                access_token = token_response.get('access_token')
                if access_token:
                    self.print_colored("✅ OAuth2 token obtained successfully", Colors.GREEN)
                    return access_token
                else:
                    self.print_colored("❌ No access_token in OAuth2 response", Colors.RED)
                    return None
            else:
                self.print_colored(f"❌ OAuth2 token request failed: {response.status_code}", Colors.RED)
                try:
                    error_details = response.json()
                    print(f"Error: {error_details}")
                except:
                    print(f"Response: {response.text}")
                return None
                
        except Exception as e:
            self.print_colored(f"❌ OAuth2 token request error: {str(e)}", Colors.RED)
            return None
    
    def validate_auth_config(self, config: ValidationConfig) -> Tuple[bool, Optional[str]]:
        """Validate authentication configuration and get access token if needed"""
        access_token = None
        
        if config.auth_type == AuthType.OAUTH2:
            access_token = self.get_oauth_token(config)
            if not access_token:
                return False, None
                
        elif config.auth_type == AuthType.API_KEY and not config.api_key:
            self.print_colored("❌ Error: API key is required for ApiKey authentication", Colors.RED)
            return False, None
        
        return True, access_token
    
    def build_request_headers(self, config: ValidationConfig, access_token: Optional[str] = None) -> Dict[str, str]:
        """Build HTTP headers for the request"""
        headers = {"Content-Type": "application/json"}
        
        # Add authentication header
        if config.auth_type == AuthType.API_KEY:
            if config.auth_config and isinstance(config.auth_config, dict):
                auth_name = config.auth_config.get('name', 'api-key')
                auth_format = config.auth_config.get('format', '{api_key}')
                headers[auth_name] = auth_format.replace('{api_key}', config.api_key or "")
            else:
                headers['api-key'] = config.api_key or ""
        elif config.auth_type == AuthType.OAUTH2 and access_token:
            headers['Authorization'] = f'Bearer {access_token}'
        
        # Add custom headers
        if config.custom_headers and isinstance(config.custom_headers, dict):
            headers.update(config.custom_headers)
        
        return headers
    
    def _build_chat_completions_url(self, config: ValidationConfig) -> str:
        """Build the chat completions URL based on configuration"""
        base_url = config.target_url.rstrip('/')
        
        if config.deployment_in_path:
            url = f"{base_url}/deployments/{config.deployment_name}/chat/completions"
        else:
            url = f"{base_url}/chat/completions"
        
        if config.inference_api_version:
            url += f"?api-version={config.inference_api_version}"
        
        return url
    
    def _build_request_body(self, config: ValidationConfig) -> Dict[str, Any]:
        """Build the request body for chat completions"""
        body = {
            "messages": [
                {
                    "role": "user",
                    "content": "Hello! This is a test message from the ModelGateway validation script. Please respond with a simple confirmation that you received this message."
                }
            ]
        }
        
        # Add model field only if deployment is not in path
        if not config.deployment_in_path:
            body["model"] = config.deployment_name
        
        return body
    
    def _generate_get_curl(self, url: str, headers: Dict[str, str]) -> str:
        """Generate curl command for GET requests"""
        curl_parts = [
            f"curl -X GET \"{url}\" \\"
        ]
        
        for header_name, header_value in headers.items():
            if header_name.lower() in ['api-key', 'authorization']:
                if header_name.lower() == 'api-key':
                    curl_parts.append(f"  -H \"{header_name}: YOUR_API_KEY\"")
                else:
                    curl_parts.append(f"  -H \"{header_name}: Bearer YOUR_TOKEN\"")
            elif header_name.lower() != 'content-type':
                curl_parts.append(f"  -H \"{header_name}: {header_value}\"")
        
        if curl_parts[-1].endswith(" \\"):
            curl_parts[-1] = curl_parts[-1][:-2]
        
        return "\n".join(curl_parts)
    
    def _generate_chat_curl(self, config: ValidationConfig, headers: Dict[str, str]) -> str:
        """Generate curl command for chat completions"""
        request_url = self._build_chat_completions_url(config)
        request_body = self._build_request_body(config)
        
        curl_parts = [f"curl -X POST \"{request_url}\" \\"]
        
        for header_name, header_value in headers.items():
            if header_name.lower() in ['api-key', 'authorization']:
                if header_name.lower() == 'api-key':
                    curl_parts.append(f"  -H \"{header_name}: YOUR_API_KEY\" \\")
                else:
                    curl_parts.append(f"  -H \"{header_name}: Bearer YOUR_TOKEN\" \\")
            else:
                curl_parts.append(f"  -H \"{header_name}: {header_value}\" \\")
        
        body_json = json.dumps(request_body, separators=(',', ':'))
        curl_parts.append(f"  -d '{body_json}'")
        
        return "\n".join(curl_parts)

    # ============================================================================
    # ERROR HANDLING METHODS
    # ============================================================================
    
    def _handle_discovery_401_error(self, config: ValidationConfig):
        """Handle 401 authentication errors in discovery phase"""
        self.print_colored(f"❌ Authentication failed: 401 - Unauthorized", Colors.RED)
        print()
        
        self.print_colored("🔧 Systematic Troubleshooting (in order of likelihood):", Colors.YELLOW)
        print()
        
        print("🔧 Option 1: FIX YOUR API KEY FIRST (Most Common - 90% of cases)")
        print("❗ Check this first - most 401 errors are wrong/expired API keys")
        if config.auth_type == AuthType.API_KEY:
            if not config.api_key:
                print("   ❌ No API key provided - add --api-key parameter")
            else:
                print("   - Double-check your API key is copied correctly (no extra spaces)")
                print("   - Verify the API key is active and not expired")
                print("   - Confirm the key has permissions for this endpoint")
                print("   - Test with a fresh API key from your gateway provider")
        print()
        
        print("🔧 Option 2: USE authConfig for different authentication headers")
        print("❗ Only try this if your API key is definitely correct")
        
        if config.auth_config and isinstance(config.auth_config, dict):
            auth_name = config.auth_config.get('name', 'api-key')
            auth_format = config.auth_config.get('format', '{api_key}')
            print("   📋 Current Custom authConfig:")
            print(f"      Header: {auth_name}")
            print(f"      Format: {auth_format}")
            print("   🔧 Try these alternatives:")
            print("      - Remove authConfig (use standard 'api-key')")
            print('        "authConfig": { "value": {} }')
        else:
            print("   📋 Current: Standard 'api-key' header")
            print("   🔧 Try these authConfig options:")
            print("      - Authorization Bearer (common for OpenAI-style APIs)")
            print('        "authConfig": {')
            print('          "value": {')
            print('            "type": "api_key",')
            print('            "name": "Authorization",')
            print('            "format": "Bearer {api_key}"')
            print('          }')
            print('        }')
            print("      - Different header names")
            print('        "authConfig": {')
            print('          "value": {')
            print('            "type": "api_key",')
            print('            "name": "x-api-key",')
            print('            "format": "{api_key}"')
            print('          }')
            print('        }')
        print()
        
        print("💡 Fix the authentication issue before proceeding")
    
    def _handle_chat_success_response(self, response: requests.Response) -> bool:
        """Handle successful chat completions response"""
        self.print_colored("✅ SUCCESS! Your gateway configuration is working correctly.", Colors.GREEN)
        print()
        
        try:
            response_json = response.json()
            if 'choices' in response_json and len(response_json['choices']) > 0:
                content = response_json['choices'][0].get('message', {}).get('content', '')
                self.print_colored("📝 Response Preview:", Colors.BLUE)
                print(content[:200] + "..." if len(content) > 200 else content)
            else:
                self.print_colored("📝 Response Preview:", Colors.BLUE)
                print("Valid response received but no content found")
        except json.JSONDecodeError:
            self.print_colored("📝 Response Preview:", Colors.BLUE)
            print("Valid response received (not JSON)")
        
        print()
        self.print_colored("🎉 Your ModelGateway connection should work when deployed to Azure AI Foundry!", Colors.GREEN)
        return True
    
    def _handle_chat_404_error(self, config: ValidationConfig) -> bool:
        """Handle 404 errors with specific guidance"""
        self.print_colored("❌ HTTP 404 - Not Found", Colors.RED)
        print()
        
        test_url = self._build_chat_completions_url(config)
        self.print_colored("🔍 We tried this URL:", Colors.BLUE)
        print(f"   {test_url}")
        print()
        
        self.print_colored("🔧 Common fixes to try:", Colors.YELLOW)
        print()
        
        print("1. Check deploymentInPath setting:")
        if config.deployment_in_path:
            print("   Current: deploymentInPath = true (deployment in URL)")
            print("   Try: deploymentInPath = false (deployment in body)")
        else:
            print("   Current: deploymentInPath = false (deployment in body)")
            print("   Try: deploymentInPath = true (deployment in URL)")
        print()
        
        print("2. API Version:")
        if config.inference_api_version:
            print(f"   Current: \"{config.inference_api_version}\"")
            print("   Try: Remove API version")
        else:
            print("   Current: No API version")
            print("   Try: Add API version (e.g., \"2024-02-01\")")
        print()
        
        return False
    
    def _handle_chat_401_error(self, config: ValidationConfig) -> bool:
        """Handle 401 authentication errors in chat completions"""
        self.print_colored("❌ HTTP 401 - Unauthorized", Colors.RED)
        print()
        
        self.print_colored("🔧 Option 1: FIX YOUR API KEY (Most Common - 90% of cases)", Colors.YELLOW)
        print("❗ Double-check your API key is correct and has permissions")
        if config.auth_type == AuthType.API_KEY:
            if not config.api_key:
                print("   ❌ No API key provided - add --api-key parameter")
            else:
                print("   - Double-check your API key is copied correctly (no extra spaces)")
                print("   - Verify the API key is active and not expired")
                print("   - Confirm the key has permissions for this endpoint")
                print("   - Test with a fresh API key from your gateway provider")
        print()
        
        self.print_colored("🔧 Option 2: USE authConfig for different authentication headers", Colors.YELLOW)
        print("❗ Only try this if your API key is definitely correct")
        
        if config.auth_config and isinstance(config.auth_config, dict):
            auth_name = config.auth_config.get('name', 'api-key')
            auth_format = config.auth_config.get('format', '{api_key}')
            print("   📋 Current Custom authConfig:")
            print(f"      Header: {auth_name}")
            print(f"      Format: {auth_format}")
            print("   🔧 Try these alternatives:")
            print("      - Remove authConfig (use standard 'api-key')")
            print('        "authConfig": { "value": {} }')
        else:
            print("   📋 Current: Standard 'api-key' header")
            print("   🔧 Try these authConfig options:")
            print("      - Authorization Bearer (common for OpenAI-style APIs)")
            print('        "authConfig": {')
            print('          "value": {')
            print('            "type": "api_key",')
            print('            "name": "Authorization",')
            print('            "format": "Bearer {api_key}"')
            print('          }')
            print('        }')
            print("      - Different header names")
            print('        "authConfig": {')
            print('          "value": {')
            print('            "type": "api_key",')
            print('            "name": "x-api-key",')
            print('            "format": "{api_key}"')
            print('          }')
            print('        }')
        print()
        
        return False
    
    def _handle_chat_400_error(self, response: requests.Response) -> bool:
        """Handle 400 bad request errors"""
        self.print_colored("❌ HTTP 400 - Bad Request", Colors.RED)
        print()
        
        try:
            error_details = response.json()
            self.print_colored("📝 Error Details:", Colors.BLUE)
            print(json.dumps(error_details, indent=2))
        except:
            print(f"Response: {response.text[:500]}")
        
        return False
    
    def _handle_chat_other_error(self, response: requests.Response) -> bool:
        """Handle other HTTP errors"""
        self.print_colored(f"❌ HTTP {response.status_code} - {response.reason}", Colors.RED)
        print()
        
        try:
            error_details = response.json()
            print(f"Error: {error_details}")
        except:
            print(f"Response: {response.text[:500]}")
        
        return False
    
    def print_configuration_summary(self, config: ValidationConfig) -> None:
        """Print configuration summary"""
        self.print_colored("📋 Configuration Summary:", Colors.BLUE)
        print(f"Target URL: {config.target_url}")
        print(f"Gateway Name: {config.gateway_name}")
        print(f"Deployment Name: {config.deployment_name}")
        print(f"Auth Type: {config.auth_type.value.title()}")
        print(f"Deployment in Path: {config.deployment_in_path}")
        print(f"Inference API Version: {config.inference_api_version or '(not set)'}")
        
        has_static = config.static_models and len(config.static_models) > 0
        discovery_str = 'Static Models' if has_static else 'Dynamic Discovery'
        print(f"Model Discovery: {discovery_str}")
        print(f"Custom Headers: {len(config.custom_headers) if config.custom_headers else 0} configured")
        print()

    # ============================================================================
    # MAIN VALIDATION ORCHESTRATOR
    # ============================================================================
    
    def validate_connection(self, config: ValidationConfig) -> bool:
        """
        Main validation orchestrator - runs all validation modules in sequence
        Returns: True if all validations pass, False otherwise
        """
        self.print_colored("🔧 ModelGateway Connection Validator - Modular Edition", Colors.BLUE)
        print("=" * 60)
        print()
        
        # Print configuration summary
        self.print_configuration_summary(config)
        
        # Get authentication token if needed
        auth_valid, access_token = self.validate_auth_config(config)
        if not auth_valid:
            return False
        
        # Build request headers
        headers = self.build_request_headers(config, access_token)
        
        # Run validation modules in sequence
        validation_steps = [
            ("Parameter Validation", lambda: self.validate_params(config)),
            ("Dynamic Discovery", lambda: self.validate_dynamic_discovery(config, headers)),
            ("Model Validation", lambda: self.validate_model(config)),
            ("Chat Completions", lambda: self.validate_chat_completions(config, headers))
        ]
        
        for step_name, validation_func in validation_steps:
            if not validation_func():
                self.print_colored(f"💡 Validation failed at: {step_name}", Colors.YELLOW)
                self.print_colored("Fix the issues above and run the script again", Colors.YELLOW)
                return False
        
        self.print_colored("🎉 All validations passed! Your ModelGateway connection is ready for deployment.", Colors.GREEN)
        return True

def main():
    parser = argparse.ArgumentParser(description='Validate ModelGateway connection configuration')
    parser.add_argument('--params', required=True, help='Path to Bicep parameter file')
    parser.add_argument('--api-key', help='API key for authentication')
    parser.add_argument('--client-secret', help='Client secret for OAuth2 authentication')
    parser.add_argument('--deployment-name', required=True, help='Name of the deployment/model to test')
    
    args = parser.parse_args()
    
    validator = ModelGatewayValidator()
    
    # Load and parse parameters
    params = validator.load_parameter_file(args.params)
    config = validator.parse_config_from_params(params, args.api_key, args.client_secret, args.deployment_name)
    
    # Run validation
    success = validator.validate_connection(config)
    
    if success:
        print()
        validator.print_colored("📚 Next Steps:", Colors.BLUE)
        print("1. Deploy your ModelGateway connection using the same parameter file")
        print("2. Test with Foundry Agents")
        print("3. Monitor performance and adjust as needed")
        sys.exit(0)
    else:
        print()
        validator.print_colored("📚 For more help:", Colors.BLUE)
        print("- See the ModelGateway setup guide: modelgateway-setup-guide-for-agents.md")
        print("- Check sample parameter files for reference")
        print("- Review your gateway documentation")
        sys.exit(1)

if __name__ == "__main__":
    main()