import os

from azure.ai.textanalytics import TextAnalyticsClient
from azure.core.credentials import AzureKeyCredential
from dotenv import find_dotenv, load_dotenv
from semantic_kernel.functions import kernel_function
from semantic_kernel.processes.kernel_process import KernelProcessStep
from utils.logger import Logger


# As part of PII Redaction step, sensitive information is redacted from the claim data using the Azure Text Analytics service.
# Sensitive fields, such as names or phone numbers will be masked with asterisks.
class PiiRedactionStep(KernelProcessStep):
    _stepName = "PiiRedactionStep"

    @kernel_function
    def execute(self, data_to_redact):
        Logger.log_step_start(self._stepName)

        COGNITIVE_SERVICES_ENDPOINT = os.getenv("COGNITIVE_SERVICES_ENDPOINT")
        COGNITIVE_SERVICES_KEY = os.getenv("COGNITIVE_SERVICES_KEY")

        redacted_text = ""

        # Create a PII Redaction client
        client = TextAnalyticsClient(
            endpoint=COGNITIVE_SERVICES_ENDPOINT, 
            credential=AzureKeyCredential(COGNITIVE_SERVICES_KEY))

        # Invoke it
        response = client.recognize_pii_entities(
            documents=[ data_to_redact ],
            categories_filter=["Person", "PhoneNumber", "Email", "Address"],
            language="en")
        result = [doc for doc in response if not doc.is_error]

        # Itearte through the result with redacted sensitive information
        for doc in result:
            redacted_text += doc.redacted_text + "\n"

        Logger.log_step_result(redacted_text)
        Logger.log_step_completion(self._stepName)
        return redacted_text

# Mocked PII Redaction Agent is a mock agent to simulate PII redaction with hardcoded data
class MockPiiRedactionStep(KernelProcessStep):
    _stepName = "MockPiiRedactionStep"

    @kernel_function
    def execute(self, data_to_redact):
        Logger.log_step_start(self._stepName)

        # Hardcoded redacted text for testing purposes
        redacted_text = """
        {
            "FullName": "********",
            "PhoneNumber": "**************",
            "EmailAddress": "********************",
            "MailingAddress": "******************************",
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
        Logger.log_step_result(redacted_text)
        Logger.log_step_completion(self._stepName)

        return redacted_text