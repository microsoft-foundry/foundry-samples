import json
import os

from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeDocumentRequest
from azure.core.credentials import AzureKeyCredential
from dotenv import find_dotenv, load_dotenv
from semantic_kernel.functions import kernel_function
from semantic_kernel.processes.kernel_process import KernelProcessStep
from utils.logger import Logger


# This step invokes Azure Document Ingelligence service to extract structured data from an image of a claim.
class DocumentIntelligenceStep(KernelProcessStep):
    _stepName = "DocumentIntelligenceStep"

    # Helper function to retrieve the value of a specific field from the document
    @staticmethod
    def get_field_value(document, field_name):
        field_value = document.fields.get(field_name)
        if field_value:
            return field_value.content
        return "Unknown"

    @kernel_function
    def execute(self, document_path): 
        Logger.log_step_start(self._stepName)

        COGNITIVE_SERVICES_ENDPOINT = os.getenv("COGNITIVE_SERVICES_ENDPOINT")
        COGNITIVE_SERVICES_KEY = os.getenv("COGNITIVE_SERVICES_KEY")

        # Define the query fields to extract
        query_fields = [
            "FullName", "PhoneNumber", "EmailAddress", "MailingAddress",
            "ProductType", "ModelNumber", "SerialNumber", "DateOfPurchase",
            "DetailedIssueDescription", "IssueStartDate", "WasDeviceDroppedOrDamaged", "AdditionalComments"
        ]

        extracted_text = ""

        with open(document_path, 'rb') as file:
            # Read the document file
            data = file.read()
            
            # Create document intelligence client
            document_intelligence_client  = DocumentIntelligenceClient(
                endpoint=COGNITIVE_SERVICES_ENDPOINT, credential=AzureKeyCredential(COGNITIVE_SERVICES_KEY)
            )

            poller = document_intelligence_client.begin_analyze_document(
                "prebuilt-layout",
                AnalyzeDocumentRequest(bytes_source=data),
                features=["queryFields"], # enable query fields extraction
                query_fields=query_fields # extract the defined query fields
            )

            result = poller.result()
            
            # Saved the extracted query fields to a dictionary
            extracted_fields = {}
            for field in query_fields:
                extracted_fields[field] = DocumentIntelligenceStep.get_field_value(result.documents[0], field)

            # Serialize the dictionary to a JSON document for another agent to consume
            extracted_text = json.dumps(extracted_fields, indent=4)

        Logger.log_step_result(extracted_text)
        Logger.log_step_completion(self._stepName)

        return extracted_text

# Document Intelligence step with mocked behavior for testing purposes
class MockDocumentIntelligenceStep(KernelProcessStep):
    _stepName = "MockDocumentIntelligenceStep"

    @kernel_function
    def execute(self, document_path):
        Logger.log_step_start(self._stepName)
        
        # Ensure the file can be opened and read
        with open(document_path, 'rb') as file:
            # Read the document file but do not process it
            data = file.read()
        
        # Return a hardcoded JSON string as the extracted data
        extracted_text = """
        {
            "FullName": "John Doe",
            "PhoneNumber": "(100) 200-3000",
            "EmailAddress": "john.doe@contoso.com",
            "MailingAddress": "123 Main St, Houston, TX 77002",
            "ProductType": "Laptop",
            "ModelNumber": "CE-12345A",
            "SerialNumber": "12345ABCDE",
            "DateOfPurchase": "1/1/2025",
            "DetailedIssueDescription": "About two days ago, my laptop (CE-12345A) suddenly stopped charging. I tried using a different power adapter, but it still wouldn't charge or turn on. The charging LED doesn't light up anymore, and the battery appears to be completely dead. I haven't dropped or spilled anything on the device. It was working fine before.",
            "IssueStartDate": "5/1/2025",
            "WasDeviceDroppedOrDamaged": "No",
            "AdditionalComments": "I rely on this for work and need it repaired or replaced as soon as possible. I've backed up all important data, so feel free to reset the device if needed."
        }
        """

        Logger.log_step_result(extracted_text)
        Logger.log_step_completion(self._stepName)

        return extracted_text