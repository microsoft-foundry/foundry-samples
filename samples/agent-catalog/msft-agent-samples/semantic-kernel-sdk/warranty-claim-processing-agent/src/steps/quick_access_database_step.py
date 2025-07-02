from semantic_kernel.functions import kernel_function
from semantic_kernel.processes.kernel_process import KernelProcessStep

from utils.logger import Logger


# Non-AI step for saving claim analysis output with redacted PII to a quick-access database widely used by the employees.
class MockQuickAccessDatabaseStep(KernelProcessStep):
    _stepName = "MockQuickAccessDatabaseStep"

    @kernel_function
    def execute(self, redacted_data):
        Logger.log_step_start(self._stepName)

        Logger.log_step_result("Saved redacted data to the quick access database.")
        Logger.log_step_completion(self._stepName)

        return redacted_data