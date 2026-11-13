// Copyright (c) Microsoft Corporation.
// Licensed under the MIT License.

// Configures OpenTelemetry console tracing. Import this module before any Azure SDK module so the
// Azure SDK instrumentation is registered before the client libraries load.

import { context, trace } from "@opentelemetry/api";
import { registerInstrumentations } from "@opentelemetry/instrumentation";
import {
  ConsoleSpanExporter,
  NodeTracerProvider,
  SimpleSpanProcessor,
} from "@opentelemetry/sdk-trace-node";
import { createAzureSdkInstrumentation } from "@azure/opentelemetry-instrumentation-azure-sdk";

export const provider = new NodeTracerProvider({
  spanProcessors: [new SimpleSpanProcessor(new ConsoleSpanExporter())],
});
provider.register();

registerInstrumentations({ instrumentations: [createAzureSdkInstrumentation()] });

export { context, trace };
