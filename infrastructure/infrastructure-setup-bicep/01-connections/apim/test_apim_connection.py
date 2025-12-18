#!/usr/bin/env python3
"""
APIM Connection Validator for Azure AI Foundry Agents

This modular validation script tests APIM connection configurations by reading Bicep parameter files
and validating all aspects of the connection before deployment to Azure AI Foundry.

Modules:
1. Parameter Validation - Validates parameter file structure and APIM-specific configuration
2. Model Discovery Validation - Tests static models or dynamic discovery endpoints  
3. Model Validation - Verifies specific model/deployment accessibility
4. Chat Completions Validation - Tests end-to-end chat completions functionality

Authentication: Supports API Key authentication with APIM subscriptions
Provider Support: AzureOpenAI and OpenAI response formats
Error Handling: Comprehensive error detection with systematic troubleshooting guidance

Usage Examples:
    # Test static models with APIM
    python3 test_apim_connection.py --params samples/parameters-static-models.json --api-key YOUR_APIM_KEY --deployment-name YOUR_DEPLOYMENT --target-url https://my-apim.azure-api.net/myapi1/models

    # Test dynamic discovery
    python3 test_apim_connection.py --params samples/parameters-dynamic-discovery.json --api-key YOUR_APIM_KEY --deployment-name YOUR_DEPLOYMENT --target-url https://my-apim.azure-api.net/myapi2/openai

    # Test custom auth configuration
    python3 test_apim_connection.py --params samples/parameters-custom-auth-config.json --api-key YOUR_APIM_KEY --deployment-name YOUR_DEPLOYMENT --target-url https://my-apim.azure-api.net/myapi
"""

import argparse
import json
import sys
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, List, Any, Tuple
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class Colors:
    """ANSI color codes for terminal output"""
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    END = '\033[0m'


class AuthType(Enum):
    """Supported authentication types"""
    API_KEY = "ApiKey"


@dataclass
class ValidationConfig:
    """Configuration parsed from Bicep parameter files"""
    # APIM-specific parameters
    apim_resource_id: str
    api_name: str
    
    # Standard connection parameters
    target_url: Optional[str]  # Provided directly via --target-url parameter
    connection_name: str
    auth_type: AuthType
    api_key: Optional[str]
    deployment_name: Optional[str]
    
    # Deployment configuration
    deployment_in_path: bool
    inference_api_version: Optional[str]
    deployment_api_version: Optional[str]
    
    # Model configuration (mutually exclusive)
    static_models: Optional[List[Dict[str, Any]]]
    model_discovery: Optional[Dict[str, str]]
    deployment_provider: Optional[str]
    
    # Custom configuration
    custom_headers: Optional[Dict[str, str]]
    auth_config: Optional[Dict[str, Any]]


class APIMConnectionValidator:
    """Modular APIM connection validator with comprehensive error handling"""
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.session = self._create_http_session()
        
    def _create_http_session(self) -> requests.Session:
        """Create HTTP session with retry strategy"""
        session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session
        
    def print_colored(self, text: str, color: str):
        """Print colored text to terminal"""
        print(f"{color}{text}{Colors.END}")
        
    def print_header(self, title: str):
        """Print section header with decorative formatting"""
        print()
        self.print_colored(f"{'='*60}", Colors.CYAN)
        self.print_colored(f"🔧 {title}", Colors.BOLD + Colors.WHITE)
        self.print_colored(f"{'='*60}", Colors.CYAN)
        print()

    # =====================================
    # MODULE 1: PARAMETER VALIDATION
    # =====================================
    
    def validate_params(self, params_file: str, api_key: Optional[str], deployment_name: Optional[str], target_url: Optional[str] = None) -> Tuple[bool, Optional[ValidationConfig]]:
        """
        Module 1: Validate parameter file structure and extract APIM configuration
        
        Returns:
            Tuple[bool, Optional[ValidationConfig]]: (success, config)
        """
        self.print_header("Parameter Validation")
        
        try:
            # Load and validate parameter file
            with open(params_file, 'r', encoding='utf-8') as f:
                params_data = json.load(f)
            
            if 'parameters' not in params_data:
                self.print_colored("❌ Error: Invalid parameter file format - missing 'parameters' section", Colors.RED)
                return False, None
                
            params = params_data['parameters']
            
            # Extract required APIM parameters
            config = ValidationConfig(
                apim_resource_id=self.extract_parameter_value(params.get('apimResourceId', {})),
                api_name=self.extract_parameter_value(params.get('apiName', {})),
                target_url=target_url,  # Use provided target URL
                connection_name=self.extract_parameter_value(params.get('connectionName', {})),
                auth_type=AuthType(self.extract_parameter_value(params.get('authType', {}))),
                api_key=api_key,
                deployment_name=deployment_name,
                deployment_in_path=self.extract_parameter_value(params.get('deploymentInPath', {})) == "true",
                inference_api_version=self.extract_parameter_value(params.get('inferenceAPIVersion', {})) or None,
                deployment_api_version=self.extract_parameter_value(params.get('deploymentAPIVersion', {})) or None,
                static_models=self.extract_parameter_value(params.get('staticModels', {})),
                model_discovery=None,
                deployment_provider=self.extract_parameter_value(params.get('deploymentProvider', {})) or None,
                custom_headers=self.extract_parameter_value(params.get('customHeaders', {})),
                auth_config=self.extract_parameter_value(params.get('authConfig', {})),
            )
            
            # Handle model discovery configuration
            if self.extract_parameter_value(params.get('listModelsEndpoint', {})):
                config.model_discovery = {
                    'listModelsEndpoint': self.extract_parameter_value(params.get('listModelsEndpoint', {})),
                    'getModelEndpoint': self.extract_parameter_value(params.get('getModelEndpoint', {})),
                    'deploymentProvider': config.deployment_provider or 'AzureOpenAI'
                }
                config.deployment_provider = config.model_discovery['deploymentProvider']
            
            # Validate target URL is provided
            if not config.target_url:
                self.print_colored("❌ Error: Target URL is required. Get it from APIM Settings tab (Base URL field).", Colors.RED)
                print()
                self.print_colored("📋 How to get Target URL:", Colors.YELLOW)
                print("1. Go to your APIM API in Azure portal")
                print("2. Click on 'Settings' tab")
                print("3. Copy the complete 'Base URL' value")
                print("4. Use that exact URL with --target-url parameter")
                print()
                print("Example: --target-url https://my-apim.azure-api.net/foundry/models")
                return False, None
            
            # Structured validation checks
            if not self._validate_basic_config(config):
                return False, None
                
            if not self._validate_discovery_method_exclusivity(config):
                return False, None
                
            if not self._validate_static_structure(config):
                return False, None
                
            if not self._validate_dynamic_structure(config):
                return False, None
                
            # Legacy validation for compatibility
            validation_result = self._validate_configuration(config)
            if not validation_result:
                return False, None
                
            # Print configuration summary
            self._print_config_summary(config)
            
            self.print_colored("✅ Parameter validation completed successfully", Colors.GREEN)
            return True, config
            
        except json.JSONDecodeError as e:
            self.print_colored(f"❌ Error: Invalid JSON in parameter file: {e}", Colors.RED)
            return False, None
        except FileNotFoundError:
            self.print_colored(f"❌ Error: Parameter file not found: {params_file}", Colors.RED)
            return False, None
        except Exception as e:
            self.print_colored(f"❌ Error parsing parameters: {e}", Colors.RED)
            return False, None
    
    def extract_parameter_value(self, param_obj: Dict[str, Any]) -> Any:
        """Extract value from Bicep parameter object"""
        if isinstance(param_obj, dict) and 'value' in param_obj:
            return param_obj['value']
        return param_obj
    
    def _validate_basic_config(self, config: ValidationConfig) -> bool:
        """Validate basic configuration requirements"""
        self.print_colored("🔍 Basic Configuration Check:", Colors.YELLOW)
        
        if not config.deployment_name:
            self.print_colored("❌ Error: deployment name is required (use --deployment-name)", Colors.RED)
            return False
        print("✅ Deployment name provided")
        
        if not config.apim_resource_id:
            self.print_colored("❌ Error: apimResourceId is required in parameter file", Colors.RED)
            return False
        print("✅ APIM Resource ID configured")
        
        if not config.api_name:
            self.print_colored("❌ Error: apiName is required in parameter file", Colors.RED)
            return False
        print("✅ API Name configured")
        
        print("✅ Basic configuration valid")
        return True
    
    def _validate_discovery_method_exclusivity(self, config: ValidationConfig) -> bool:
        """Validate exactly one discovery method is configured"""
        self.print_colored("🔍 Model Discovery Method Check:", Colors.YELLOW)
        
        has_static = config.static_models and len(config.static_models) > 0
        has_dynamic = config.model_discovery is not None
        
        if has_static and has_dynamic:
            self.print_colored("❌ Error: Both static models and dynamic discovery configured", Colors.RED)
            self.print_colored("You must configure exactly one model discovery method, not both.", Colors.RED)
            print()
            self.print_colored("📋 Fix in your parameter file:", Colors.BLUE)
            print("Choose one of these approaches:")
            print("1. Use static models: Keep 'staticModels' and remove dynamic discovery parameters")
            print("   - Remove: listModelsEndpoint, getModelEndpoint, deploymentProvider")
            print("2. Use dynamic discovery: Remove 'staticModels' and keep dynamic parameters")
            print("   - Keep: listModelsEndpoint, getModelEndpoint, deploymentProvider")
            return False
        
        elif not has_static and not has_dynamic:
            self.print_colored("❌ Error: No model discovery configuration found", Colors.RED)
            self.print_colored("Your parameter file must configure exactly one model discovery method.", Colors.RED)
            print()
            self.print_colored("📋 Fix in your parameter file:", Colors.BLUE)
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
            
        self.print_colored("🔍 Static Model Structure Check:", Colors.YELLOW)
        
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
                self.print_colored(f"⚠️ Warning: staticModels[{i}].properties.model missing 'format' field", Colors.YELLOW)
        
        print(f"✅ Static model structure valid ({len(config.static_models)} models)")
        return True
    
    def _validate_dynamic_structure(self, config: ValidationConfig) -> bool:
        """Validate dynamic discovery configuration structure"""
        has_dynamic = config.model_discovery is not None
        
        if not has_dynamic:
            return True  # No dynamic discovery configured
            
        self.print_colored("🔍 Dynamic Discovery Structure Check:", Colors.YELLOW)
        
        list_endpoint = config.model_discovery.get('listModelsEndpoint')
        get_endpoint = config.model_discovery.get('getModelEndpoint')
        deployment_provider = config.model_discovery.get('deploymentProvider')
        
        if not list_endpoint:
            self.print_colored("❌ Error: Missing listModelsEndpoint in model discovery", Colors.RED)
            return False
            
        if not get_endpoint:
            self.print_colored("❌ Error: Missing getModelEndpoint in model discovery", Colors.RED)
            return False
            
        if not deployment_provider:
            self.print_colored("❌ Error: Missing deploymentProvider in model discovery", Colors.RED)
            return False
        
        # Validate deploymentProvider value
        valid_providers = ["AzureOpenAI", "OpenAI"]
        if deployment_provider not in valid_providers:
            self.print_colored("❌ Error: Invalid deploymentProvider value", Colors.RED)
            self.print_colored(f"Current value: {deployment_provider}", Colors.RED)
            print()
            self.print_colored("📋 Fix in your parameter file:", Colors.BLUE)
            print("Set deploymentProvider to one of these exact values:")
            for provider in valid_providers:
                print(f"  - \"{provider}\"")
            return False
        
        # Validate getModelEndpoint template
        if "{deploymentName}" not in get_endpoint:
            self.print_colored("❌ Error: getModelEndpoint must contain '{deploymentName}' template", Colors.RED)
            self.print_colored(f"Current value: {get_endpoint}", Colors.RED)
            print()
            self.print_colored("📋 Fix in your parameter file:", Colors.BLUE)
            print("Update getModelEndpoint to include the {deploymentName} placeholder:")
            print("Example: \"/deployments/{deploymentName}\" or \"/models/{deploymentName}\"")
            return False
        
        print("✅ Dynamic discovery structure valid")
        return True
    
    def _validate_configuration(self, config: ValidationConfig) -> bool:
        """Validate configuration consistency"""
        errors = []
        
        # Check for required parameters
        if not config.apim_resource_id:
            errors.append("Missing required parameter: apimResourceId")
        if not config.api_name:
            errors.append("Missing required parameter: apiName")
        if not config.connection_name:
            errors.append("Missing required parameter: connectionName")
            
        # Check authentication
        if config.auth_type == AuthType.API_KEY and not config.api_key:
            errors.append("API key is required for ApiKey authentication")
            
        # Check model configuration (must have either static models OR dynamic discovery)
        has_static = config.static_models and len(config.static_models) > 0
        has_dynamic = config.model_discovery is not None
        
        if has_static and has_dynamic:
            errors.append("Cannot configure both static models and dynamic discovery")
        elif not has_static and not has_dynamic:
            errors.append("Must configure either static models OR dynamic discovery")
            
        if errors:
            for error in errors:
                self.print_colored(f"❌ {error}", Colors.RED)
            return False
            
        return True
    
    def _print_config_summary(self, config: ValidationConfig):
        """Print configuration summary"""
        self.print_colored("📋 Configuration Summary:", Colors.BLUE)
        print(f"   Target URL: {config.target_url}")
        print(f"   API Name: {config.api_name}")
        print(f"   Connection Name: {config.connection_name}")
        print(f"   Auth Type: {config.auth_type.value}")
        print(f"   Deployment Name: {config.deployment_name}")
        print(f"   Deployment in Path: {config.deployment_in_path}")
        if config.inference_api_version:
            print(f"   Inference API Version: {config.inference_api_version}")
        if config.deployment_api_version:
            print(f"   Deployment API Version: {config.deployment_api_version}")
        
        # Model configuration
        if config.static_models:
            print(f"   Static Models: {len(config.static_models)} configured")
        elif config.model_discovery:
            print(f"   Dynamic Discovery: {config.deployment_provider} format")
            
        if config.custom_headers:
            print(f"   Custom Headers: {len(config.custom_headers)} configured")
        if config.auth_config:
            print(f"   Custom Auth Config: Configured")

    # =====================================
    # MODULE 2: MODEL DISCOVERY VALIDATION
    # =====================================
    
    def validate_discovery(self, config: ValidationConfig) -> bool:
        """
        Module 2: Validate model discovery (static models or dynamic endpoints)
        
        Returns:
            bool: True if discovery validation passes
        """
        self.print_header("Model Discovery Validation")
        
        if config.static_models:
            return self._validate_static_models(config)
        elif config.model_discovery:
            return self._validate_dynamic_discovery(config)
        else:
            self.print_colored("❌ Error: No model discovery configuration found", Colors.RED)
            return False
    
    def _validate_static_models(self, config: ValidationConfig) -> bool:
        """Validate static model configuration"""
        self.print_colored("🔍 Validating static models configuration...", Colors.BLUE)
        
        if not config.static_models or len(config.static_models) == 0:
            self.print_colored("❌ Error: No static models configured", Colors.RED)
            return False
            
        # Validate each static model
        for i, model in enumerate(config.static_models):
            model_name = model.get('name', f'Model {i+1}')
            self.print_colored(f"   📋 Validating model: {model_name}", Colors.CYAN)
            
            if 'properties' not in model:
                self.print_colored(f"   ❌ Missing 'properties' in model {model_name}", Colors.RED)
                return False
                
            props = model['properties']
            if 'model' not in props:
                self.print_colored(f"   ❌ Missing 'model' in properties for {model_name}", Colors.RED)
                return False
                
            model_info = props['model']
            required_fields = ['name', 'format']
            for field in required_fields:
                if field not in model_info:
                    self.print_colored(f"   ❌ Missing '{field}' in model info for {model_name}", Colors.RED)
                    return False
                    
            # Validate model format
            model_format = model_info.get('format')
            valid_formats = ['OpenAI', 'Anthropic', 'NonOpenAI']
            if model_format not in valid_formats:
                self.print_colored(f"   ⚠️ Warning: Unexpected model format '{model_format}' for {model_name}", Colors.YELLOW)
                self.print_colored(f"      Valid formats: {', '.join(valid_formats)}", Colors.YELLOW)
                
            print(f"      Model: {model_info.get('name')}")
            print(f"      Version: {model_info.get('version', 'Not specified')}")
            print(f"      Format: {model_info.get('format')}")
            
        self.print_colored(f"✅ Static models validation completed - {len(config.static_models)} models configured", Colors.GREEN)
        return True
    
    def _validate_dynamic_discovery(self, config: ValidationConfig) -> bool:
        """Validate dynamic discovery endpoints"""
        self.print_colored("🔍 Testing dynamic discovery endpoints...", Colors.BLUE)
        
        # Validate discovery configuration
        if not config.model_discovery:
            self.print_colored("❌ Error: No model discovery configuration", Colors.RED)
            return False
            
        list_endpoint = config.model_discovery.get('listModelsEndpoint')
        get_endpoint = config.model_discovery.get('getModelEndpoint')
        
        if not list_endpoint:
            self.print_colored("❌ Error: Missing listModelsEndpoint in model discovery", Colors.RED)
            return False
            
        if not get_endpoint:
            self.print_colored("❌ Error: Missing getModelEndpoint in model discovery", Colors.RED)
            return False
            
        # Validate getModelEndpoint template
        if "{deploymentName}" not in get_endpoint:
            self.print_colored("❌ Error: getModelEndpoint must contain '{deploymentName}' template", Colors.RED)
            self.print_colored(f"Current value: {get_endpoint}", Colors.YELLOW)
            print()
            self.print_colored("📋 Fix in your parameter file:", Colors.YELLOW)
            print("Update getModelEndpoint to include the {deploymentName} placeholder:")
            print("Example: \"/deployments/{deploymentName}\" or \"/models/{deploymentName}\"")
            return False
            
        # Test list models endpoint
        list_url = f"{config.target_url}{list_endpoint}"
        if config.deployment_api_version:
            list_url += f"?api-version={config.deployment_api_version}"
            
        self.print_colored(f"🔗 Testing list models endpoint:", Colors.BLUE)
        print(f"   URL: {list_url}")
        
        # Build headers for discovery request
        headers = self.build_request_headers(config)
        
        # Generate curl command for debugging
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
                print("The list models endpoint is not working correctly")
                try:
                    error_details = response.json()
                    print(f"Error: {error_details}")
                except:
                    print(f"Response: {response.text[:200]}")
                return False
            
            self.print_colored("✅ List models endpoint working", Colors.GREEN)
            
            # Parse and validate response format
            try:
                models_data = response.json()
                models_found = self._parse_models_list(models_data, config.deployment_provider)
                
                if not models_found:
                    self.print_colored("❌ Error: No models found in list response", Colors.RED)
                    self.print_colored("📋 Actual Response:", Colors.YELLOW)
                    print(f"   {json.dumps(models_data, indent=2)[:500]}{'...' if len(str(models_data)) > 500 else ''}")
                    self.print_colored("⚠️ Response not in expected format for dynamic discovery", Colors.YELLOW)
                    return False
                    
                self.print_colored(f"✅ Found {len(models_found)} models in discovery response", Colors.GREEN)
                
                # Test get model endpoint with first model
                if models_found and config.deployment_name:
                    return self._test_get_model_endpoint(config, models_found)
                    
                return True
                
            except json.JSONDecodeError:
                self.print_colored("❌ Error: List models response is not valid JSON", Colors.RED)
                return False
                
        except Exception as e:
            self.print_colored(f"❌ Error testing list models endpoint: {str(e)}", Colors.RED)
            return False
    
    def _parse_models_list(self, models_data: Dict[str, Any], provider: str) -> List[str]:
        """Parse models list response based on provider format"""
        models = []
        
        if provider == "AzureOpenAI":
            # Azure OpenAI format: { "value": [...] }
            if 'value' in models_data:
                for model in models_data['value']:
                    if 'name' in model:
                        models.append(model['name'])
                        
        else:  # OpenAI format
            # OpenAI format: { "data": [...] }
            if 'data' in models_data:
                for model in models_data['data']:
                    if 'id' in model:
                        models.append(model['id'])
                        
        return models
    
    def _test_get_model_endpoint(self, config: ValidationConfig, available_models: List[str]) -> bool:
        """Test the get model endpoint"""
        if not config.deployment_name:
            self.print_colored("⚠️ Warning: No deployment name provided, skipping get model test", Colors.YELLOW)
            return True
            
        # Check if the requested deployment exists in available models
        if config.deployment_name not in available_models:
            self.print_colored(f"❌ Error: Deployment '{config.deployment_name}' not found in available models", Colors.RED)
            self.print_colored(f"   Available models: {', '.join(available_models[:5])}{'...' if len(available_models) > 5 else ''}", Colors.YELLOW)
            return False
        
        # Test get model endpoint
        get_endpoint_template = config.model_discovery['getModelEndpoint']
        if "{deploymentName}" not in get_endpoint_template:
            self.print_colored("❌ Error: getModelEndpoint missing {deploymentName} template", Colors.RED)
            self.print_colored(f"Current value: {get_endpoint_template}", Colors.YELLOW)
            return False
            
        get_endpoint = get_endpoint_template.replace('{deploymentName}', config.deployment_name)
        get_url = f"{config.target_url}{get_endpoint}"
        if config.deployment_api_version:
            get_url += f"?api-version={config.deployment_api_version}"
            
        self.print_colored(f"🔗 Testing get model endpoint:", Colors.BLUE)
        print(f"   URL: {get_url}")
        
        headers = self.build_request_headers(config)
        
        # Generate curl command for debugging
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
                
                if config.deployment_provider == "AzureOpenAI":
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
                        self.print_colored("   Fix: Change deploymentProvider to 'AzureOpenAI'", Colors.YELLOW)
                        return False
                    elif 'id' in model_data:
                        model_id = model_data['id']
                        print(f"   Model ID: {model_id}")
                        
                        if model_id != config.deployment_name:
                            self.print_colored(f"⚠️ Warning: Model ID '{model_id}' doesn't match deployment name '{config.deployment_name}'", Colors.YELLOW)
                    else:
                        self.print_colored("❌ Error: Unexpected response format for OpenAI provider", Colors.RED)
                        self.print_colored("📋 Actual Response:", Colors.YELLOW)
                        print(f"   {json.dumps(model_data, indent=2)[:500]}{'...' if len(str(model_data)) > 500 else ''}")
                        self.print_colored("⚠️ Response not in expected OpenAI format for dynamic discovery", Colors.YELLOW)
                        return False
                
                return True
                
            except json.JSONDecodeError:
                self.print_colored("❌ Error: Get model response is not valid JSON", Colors.RED)
                return False
                
        except Exception as e:
            self.print_colored(f"❌ Error testing get model endpoint: {str(e)}", Colors.RED)
            return False

    # =====================================
    # MODULE 3: MODEL VALIDATION
    # =====================================
    
    def validate_model(self, config: ValidationConfig) -> bool:
        """
        Module 3: Validate specific model/deployment accessibility
        
        Returns:
            bool: True if model validation passes
        """
        self.print_header("Model Validation")
        
        if not config.deployment_name:
            self.print_colored("⚠️ Warning: No deployment name provided, skipping model validation", Colors.YELLOW)
            return True
            
        if config.static_models:
            return self._validate_static_model_exists(config)
        elif config.model_discovery:
            # Dynamic discovery validation was already done in discovery module
            self.print_colored(f"✅ Model '{config.deployment_name}' validation completed (via dynamic discovery)", Colors.GREEN)
            return True
        else:
            self.print_colored("❌ Error: No model configuration available for validation", Colors.RED)
            return False
    
    def _validate_static_model_exists(self, config: ValidationConfig) -> bool:
        """Validate that the specified deployment exists in static models"""
        self.print_colored(f"🔍 Checking if deployment '{config.deployment_name}' exists in static models...", Colors.BLUE)
        
        if not config.static_models:
            self.print_colored("❌ Error: No static models configured", Colors.RED)
            return False
            
        # Find the deployment in static models
        for model in config.static_models:
            if model.get('name') == config.deployment_name:
                model_info = model.get('properties', {}).get('model', {})
                self.print_colored(f"✅ Found deployment '{config.deployment_name}'", Colors.GREEN)
                print(f"   Model: {model_info.get('name', 'Unknown')}")
                print(f"   Version: {model_info.get('version', 'Not specified')}")
                print(f"   Format: {model_info.get('format', 'Unknown')}")
                return True
                
        # Deployment not found
        self.print_colored(f"❌ Error: Deployment '{config.deployment_name}' not found in static models", Colors.RED)
        
        available_models = [model.get('name', 'Unknown') for model in config.static_models]
        self.print_colored("   Available deployments:", Colors.YELLOW)
        for model_name in available_models:
            print(f"     - {model_name}")
            
        return False

    # =====================================
    # MODULE 4: CHAT COMPLETIONS VALIDATION
    # =====================================
    
    def validate_chat_completions(self, config: ValidationConfig) -> bool:
        """
        Module 4: Test end-to-end chat completions functionality
        
        Returns:
            bool: True if chat completions validation passes
        """
        self.print_header("Chat Completions Validation")
        
        if not config.deployment_name:
            self.print_colored("❌ Error: Deployment name is required for chat completions testing", Colors.RED)
            return False
            
        # Build chat completions URL
        chat_url = self._build_chat_completions_url(config)
        
        self.print_colored("🔗 Testing chat completions endpoint:", Colors.BLUE)
        print(f"   URL: {chat_url}")
        print()
        
        # Build headers and request body
        headers = self.build_request_headers(config)
        request_body = self._build_chat_request_body(config)
        
        # Generate curl command for debugging
        curl_command = self._generate_post_curl(chat_url, headers, request_body)
        print(curl_command)
        print()
        
        self.print_colored("🚀 Making chat completions request...", Colors.BLUE)
        start_time = time.time()
        
        try:
            response = self.session.post(chat_url, headers=headers, json=request_body, timeout=30)
            response_time = time.time() - start_time
            
            self.print_colored("📊 Response Summary:", Colors.BLUE)
            print(f"   HTTP Status: {response.status_code}")
            print(f"   Response Time: {response_time:.2f}s")
            print()
            
            # Handle different response codes
            if response.status_code == 200:
                return self._handle_chat_success_response(response)
            elif response.status_code == 401:
                return self._handle_chat_401_error(config)
            elif response.status_code == 404:
                return self._handle_chat_404_error(config)
            elif response.status_code == 400:
                return self._handle_chat_400_error(response)
            else:
                self.print_colored(f"❌ Unexpected response: {response.status_code}", Colors.RED)
                try:
                    error_details = response.json()
                    print(f"Error details: {error_details}")
                except:
                    print(f"Response: {response.text[:500]}")
                return False
                
        except requests.exceptions.Timeout:
            self.print_colored("❌ Request timed out (30 seconds)", Colors.RED)
            self.print_colored("   This might indicate a slow gateway or network issue", Colors.YELLOW)
            return False
        except requests.exceptions.ConnectionError as e:
            self.print_colored(f"❌ Connection error: {str(e)}", Colors.RED)
            self.print_colored("   Check if the target URL is correct and accessible", Colors.YELLOW)
            return False
        except Exception as e:
            self.print_colored(f"❌ Error making chat completions request: {str(e)}", Colors.RED)
            return False
    
    def _build_chat_completions_url(self, config: ValidationConfig) -> str:
        """Build the chat completions URL based on configuration"""
        if config.deployment_in_path:
            # Model/deployment in URL path
            path = f"/deployments/{config.deployment_name}/chat/completions"
        else:
            # Model in request body
            path = "/chat/completions"
            
        url = f"{config.target_url}{path}"
        
        # Add API version if specified
        if config.inference_api_version:
            url += f"?api-version={config.inference_api_version}"
            
        return url
    
    def _build_chat_request_body(self, config: ValidationConfig) -> Dict[str, Any]:
        """Build chat completions request body"""
        request_body = {
            "messages": [
                {
                    "role": "user",
                    "content": "Hello! This is a test message from the APIM connection validation script. Please respond briefly."
                }
            ]
        }
        
        # Add model field if not in path
        if not config.deployment_in_path:
            request_body["model"] = config.deployment_name
            
        return request_body
    
    def build_request_headers(self, config: ValidationConfig) -> Dict[str, str]:
        """Build HTTP headers for the request"""
        headers = {"Content-Type": "application/json"}
        
        # Add authentication header
        if config.auth_type == AuthType.API_KEY:
            if config.auth_config and isinstance(config.auth_config, dict):
                auth_name = config.auth_config.get('name') or 'api_key'
                auth_format = config.auth_config.get('format', '{api_key}')
                headers[auth_name] = auth_format.replace('{api_key}', config.api_key or "")
            else:
                # Default APIM subscription key header
                headers['api-key'] = config.api_key or ""
        
        # Add custom headers
        if config.custom_headers and isinstance(config.custom_headers, dict):
            headers.update(config.custom_headers)
            
        return headers

    # =====================================
    # CURL COMMAND GENERATION
    # =====================================
    
    def _generate_get_curl(self, url: str, headers: Dict[str, str]) -> str:
        """Generate curl command for GET requests"""
        curl_parts = ["curl", "-X", "GET", f'"{url}"']
        
        for key, value in headers.items():
            if key.lower() != 'content-type':  # Skip content-type for GET
                curl_parts.extend(["-H", f'"{key}: {value}"'])
        
        return " \\\n  ".join(curl_parts)
    
    def _generate_post_curl(self, url: str, headers: Dict[str, str], body: Dict[str, Any]) -> str:
        """Generate curl command for POST requests"""
        curl_parts = ["curl", "-X", "POST", f'"{url}"']
        
        for key, value in headers.items():
            curl_parts.extend(["-H", f'"{key}: {value}"'])
        
        body_str = json.dumps(body, indent=2)
        curl_parts.extend(["-d", f"'{body_str}'"])
        
        return " \\\n  ".join(curl_parts)

    # =====================================
    # ERROR HANDLING METHODS
    # =====================================
    
    def _handle_discovery_401_error(self, config: ValidationConfig):
        """Handle 401 authentication errors in discovery phase"""
        self.print_colored(f"❌ Authentication failed: 401 - Unauthorized", Colors.RED)
        print()
        
        self.print_colored("🔧 Systematic Troubleshooting (in order of likelihood):", Colors.YELLOW)
        print()
        
        print("🔧 Option 1: FIX YOUR APIM SUBSCRIPTION KEY FIRST (Most Common - 90% of cases)")
        print("❗ Check this first - most 401 errors are wrong/expired APIM subscription keys")
        if config.auth_type == AuthType.API_KEY:
            if not config.api_key:
                print("   ❌ No APIM subscription key provided - add --api-key parameter")
            else:
                print("   - Double-check your APIM subscription key is copied correctly (no extra spaces)")
                print("   - Verify the subscription key is active and not expired")
                print("   - Confirm the subscription has access to this API")
                print("   - Test with a fresh subscription key from APIM portal")
        print()
                
        print("💡 Fix the authentication issue before proceeding")
    
    def _handle_chat_success_response(self, response: requests.Response) -> bool:
        """Handle successful chat completions response"""
        self.print_colored("✅ SUCCESS! Your APIM configuration is working correctly.", Colors.GREEN)
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
        self.print_colored("🎉 Your APIM connection should work when deployed to Azure AI Foundry!", Colors.GREEN)
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
        
        print("3. Check APIM API configuration:")
        print("   - Verify the API path in APIM matches expected endpoints")
        print("   - Check if APIM API policies are blocking requests")
        print("   - Ensure chat completions operations are configured in APIM")
        print()
        
        return False
    
    def _handle_chat_401_error(self, config: ValidationConfig) -> bool:
        """Handle 401 authentication errors in chat completions"""
        self.print_colored("❌ HTTP 401 - Unauthorized", Colors.RED)
        print()
        
        self.print_colored("🔧 Option 1: FIX YOUR APIM SUBSCRIPTION KEY (Most Common - 90% of cases)", Colors.YELLOW)
        print("❗ Double-check your APIM subscription key is correct and has permissions")
        if config.auth_type == AuthType.API_KEY:
            if not config.api_key:
                print("   ❌ No APIM subscription key provided - add --api-key parameter")
            else:
                print("   - Double-check your APIM subscription key is copied correctly (no extra spaces)")
                print("   - Verify the subscription key is active and not expired")
                print("   - Confirm the subscription has access to this API")
                print("   - Test with a fresh subscription key from APIM portal")
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
        
        print()
        self.print_colored("🔧 Common fixes:", Colors.YELLOW)
        print("- Check if the model name/deployment is correct")
        print("- Verify the request body format matches API expectations")
        print("- Ensure APIM policies aren't modifying the request")
        print()
        
        return False

    # =====================================
    # MAIN VALIDATION ORCHESTRATOR
    # =====================================
    
    def run_validation(self, params_file: str, api_key: Optional[str], deployment_name: Optional[str], target_url: Optional[str] = None) -> bool:
        """
        Run complete modular validation of APIM connection
        
        Returns:
            bool: True if all validation modules pass
        """
        self.print_colored("🔧 APIM Connection Validator", Colors.BOLD + Colors.WHITE)
        self.print_colored("="*60, Colors.CYAN)
        print(f"Parameter file: {params_file}")
        if deployment_name:
            print(f"Testing deployment: {deployment_name}")
        print()
        
        # Module 1: Parameter Validation
        params_valid, config = self.validate_params(params_file, api_key, deployment_name, target_url)
        if not params_valid or not config:
            return False
        
        # Module 2: Model Discovery Validation  
        discovery_valid = self.validate_discovery(config)
        if not discovery_valid:
            return False
        
        # Module 3: Model Validation
        model_valid = self.validate_model(config)
        if not model_valid:
            return False
        
        # Module 4: Chat Completions Validation
        chat_valid = self.validate_chat_completions(config)
        if not chat_valid:
            return False
        
        # All modules passed
        print()
        self.print_colored("="*60, Colors.GREEN)
        self.print_colored("🎉 ALL VALIDATION MODULES PASSED!", Colors.BOLD + Colors.GREEN)
        self.print_colored("="*60, Colors.GREEN)
        print()
        self.print_colored("✅ Your APIM connection configuration is ready for deployment to Azure AI Foundry!", Colors.GREEN)
        self.print_colored("✅ This configuration should work correctly when used with the Agents SDK.", Colors.GREEN)
        print()
        
        return True


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Validate APIM connection configuration for Azure AI Foundry Agents",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test static models configuration
  %(prog)s --params samples/parameters-static-models.json --api-key YOUR_APIM_KEY --deployment-name YOUR_DEPLOYMENT --target-url https://my-apim.azure-api.net/foundry/models

  # Test dynamic discovery
  %(prog)s --params samples/parameters-dynamic-discovery.json --api-key YOUR_APIM_KEY --deployment-name YOUR_DEPLOYMENT --target-url https://my-apim.azure-api.net/foundry/models

  # Test custom authentication
  %(prog)s --params samples/parameters-custom-auth-config.json --api-key YOUR_APIM_KEY --deployment-name YOUR_DEPLOYMENT --target-url https://my-apim.azure-api.net/foundry/models

The script validates your APIM connection by testing:
1. Parameter validation and configuration parsing
2. Model discovery (static models or dynamic endpoints)
3. Model/deployment accessibility
4. End-to-end chat completions functionality

All validation is done against your actual APIM gateway to ensure the configuration
will work when deployed to Azure AI Foundry for use with the Agents SDK.
        """
    )
    
    parser.add_argument(
        '--params', 
        required=True,
        help='Path to Bicep parameter file (e.g., samples/parameters-static-models.json)'
    )
    
    parser.add_argument(
        '--api-key',
        required=True,
        help='APIM subscription key for authentication'
    )
    
    parser.add_argument(
        '--deployment-name',
        required=True,
        help='Name of the model deployment to test'
    )
    
    parser.add_argument(
        '--target-url',
        required=True,
        help='Complete base URL from APIM Settings tab (e.g., https://my-apim.azure-api.net/foundry/models)'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose output for debugging'
    )
    
    args = parser.parse_args()
    
    # Create validator and run validation
    validator = APIMConnectionValidator(verbose=args.verbose)
    
    try:
        success = validator.run_validation(
            params_file=args.params,
            api_key=args.api_key,
            deployment_name=args.deployment_name,
            target_url=args.target_url
        )
        
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        print()
        validator.print_colored("❌ Validation interrupted by user", Colors.RED)
        sys.exit(1)
    except Exception as e:
        validator.print_colored(f"❌ Unexpected error: {str(e)}", Colors.RED)
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()