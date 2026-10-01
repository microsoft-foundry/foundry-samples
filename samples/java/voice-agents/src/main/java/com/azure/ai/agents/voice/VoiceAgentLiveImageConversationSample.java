// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

package com.azure.ai.agents.voice;

import com.azure.ai.agents.AgentsClientBuilder;
import com.azure.ai.agents.BetaVoiceAgentWebSocketClient;
import com.azure.ai.agents.BetaVoiceAgentWebSocketSessionClient;
import com.azure.ai.agents.models.RealtimeErrorEvent;
import com.azure.ai.agents.models.RealtimeResponseAudioTranscriptDoneEvent;
import com.azure.ai.agents.models.RealtimeResponseDoneEvent;
import com.azure.ai.agents.models.RealtimeResponseTextDoneEvent;
import com.azure.ai.agents.models.RealtimeServerEvent;
import com.azure.core.util.BinaryData;
import com.azure.core.util.Configuration;
import com.azure.identity.DefaultAzureCredentialBuilder;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Consumer;

/**
 * Sends one text-and-image turn to an existing Microsoft Foundry voice agent.
 */
public class VoiceAgentLiveImageConversationSample {
    private static final int MAX_IMAGE_BYTES = 8 * 1024 * 1024;
    private static final String DEFAULT_IMAGE_PROMPT = "Describe this image briefly.";

    public static void main(String[] args) throws IOException {
        if (args.length == 1 && "--self-test".equals(args[0])) {
            selfTest();
            return;
        }

        Configuration configuration = Configuration.getGlobalConfiguration();
        String endpoint = requireConfiguration(configuration, "FOUNDRY_PROJECT_ENDPOINT");
        String agentName = requireConfiguration(configuration, "FOUNDRY_VOICE_AGENT_NAME");
        String imagePath = requireConfiguration(configuration, "FOUNDRY_VOICE_AGENT_IMAGE_PATH");
        String prompt = configuration.get(
            "FOUNDRY_VOICE_AGENT_IMAGE_PROMPT",
            DEFAULT_IMAGE_PROMPT);
        BinaryData event = buildImageEvent(Paths.get(imagePath), prompt);

        AgentsClientBuilder builder = new AgentsClientBuilder()
            .credential(new DefaultAzureCredentialBuilder().build())
            .endpoint(endpoint)
            .allowPreview(true);
        BetaVoiceAgentWebSocketClient realtime
            = builder.beta().buildBetaVoiceAgentWebSocketClient();

        try (BetaVoiceAgentWebSocketSessionClient session
                = realtime.openWebSocketSession(agentName)) {
            sendImageTurn(session, event);

            boolean completed = false;
            for (RealtimeServerEvent serverEvent : session.receiveEvents()) {
                if (serverEvent instanceof RealtimeResponseAudioTranscriptDoneEvent) {
                    System.out.println("Agent: "
                        + ((RealtimeResponseAudioTranscriptDoneEvent) serverEvent)
                            .getTranscript());
                } else if (serverEvent instanceof RealtimeResponseTextDoneEvent) {
                    System.out.println("Agent: "
                        + ((RealtimeResponseTextDoneEvent) serverEvent).getText());
                } else if (serverEvent instanceof RealtimeErrorEvent) {
                    throw new IllegalStateException(
                        ((RealtimeErrorEvent) serverEvent).getError().message());
                } else if (serverEvent instanceof RealtimeResponseDoneEvent) {
                    String status = ((RealtimeResponseDoneEvent) serverEvent)
                        .getResponse().getStatus().toString();
                    if (!"completed".equalsIgnoreCase(status)) {
                        throw new IllegalStateException(
                            "Voice response ended with status: " + status);
                    }
                    completed = true;
                    break;
                }
            }
            if (!completed) {
                throw new IllegalStateException(
                    "The connection closed before response.done.");
            }
        }
    }

    private static BinaryData buildImageEvent(Path imagePath, String prompt)
        throws IOException {
        long fileSize = Files.size(imagePath);
        if (fileSize > Integer.MAX_VALUE) {
            throw new IllegalArgumentException(
                "Choose an image no larger than 8 MiB.");
        }
        validateImage(imagePath.getFileName().toString(), (int) fileSize);
        byte[] image = Files.readAllBytes(imagePath);
        String mediaType = validateImage(
            imagePath.getFileName().toString(),
            image.length);
        String dataUrl = "data:" + mediaType + ";base64,"
            + Base64.getEncoder().encodeToString(image);
        return buildImageEvent(dataUrl, prompt);
    }

    private static String validateImage(String filename, int byteLength) {
        filename = filename.toLowerCase(Locale.ROOT);
        String mediaType;
        if (filename.endsWith(".jpg") || filename.endsWith(".jpeg")) {
            mediaType = "image/jpeg";
        } else if (filename.endsWith(".png")) {
            mediaType = "image/png";
        } else if (filename.endsWith(".webp")) {
            mediaType = "image/webp";
        } else {
            throw new IllegalArgumentException(
                "Choose a JPEG, PNG, or WebP image.");
        }

        if (byteLength == 0) {
            throw new IllegalArgumentException("The image must not be empty.");
        }
        if (byteLength > MAX_IMAGE_BYTES) {
            throw new IllegalArgumentException(
                "Choose an image no larger than 8 MiB.");
        }
        return mediaType;
    }

    // The Java realtime models don't yet expose an image content factory, so
    // this sample sends the complete client event through sendEvent(BinaryData).
    // <image_turn>
    private static BinaryData buildImageEvent(String dataUrl, String prompt) {
        Map<String, Object> text = new LinkedHashMap<>();
        text.put("type", "input_text");
        text.put(
            "text",
            prompt == null || prompt.trim().isEmpty()
                ? DEFAULT_IMAGE_PROMPT
                : prompt.trim());

        Map<String, Object> image = new LinkedHashMap<>();
        image.put("type", "input_image");
        image.put("image_url", dataUrl);
        image.put("detail", "low");

        List<Map<String, Object>> content = new ArrayList<>();
        content.add(text);
        content.add(image);

        Map<String, Object> item = new LinkedHashMap<>();
        item.put("type", "message");
        item.put("role", "user");
        item.put("content", content);

        Map<String, Object> event = new LinkedHashMap<>();
        event.put("type", "conversation.item.create");
        event.put("item", item);
        return BinaryData.fromObject(event);
    }

    private static void sendImageTurn(
        BetaVoiceAgentWebSocketSessionClient session,
        BinaryData event) {
        session.sendEvent(event);
        session.createResponse();
    }
    // </image_turn>

    private static void sendImageTurnForTest(
        Consumer<BinaryData> sendItem,
        Runnable requestResponse,
        BinaryData event) {
        sendItem.accept(event);
        requestResponse.run();
    }

    @SuppressWarnings("unchecked")
    private static void selfTest() {
        BinaryData event = buildImageEvent(
            "data:image/png;base64,iVBORw==",
            "  ");
        AtomicInteger itemCount = new AtomicInteger();
        AtomicInteger responseCount = new AtomicInteger();
        sendImageTurnForTest(
            value -> {
                assertCondition(value == event);
                itemCount.incrementAndGet();
            },
            responseCount::incrementAndGet,
            event);

        Map<String, Object> root = event.toObject(Map.class);
        Map<String, Object> item = (Map<String, Object>) root.get("item");
        List<Map<String, Object>> content
            = (List<Map<String, Object>>) item.get("content");
        assertCondition(content.size() == 2);
        assertCondition("input_text".equals(content.get(0).get("type")));
        assertCondition(DEFAULT_IMAGE_PROMPT.equals(content.get(0).get("text")));
        assertCondition("input_image".equals(content.get(1).get("type")));
        assertCondition(content.get(1).get("image_url").toString()
            .startsWith("data:image/png;base64,"));
        assertCondition("low".equals(content.get(1).get("detail")));
        assertCondition(itemCount.get() == 1);
        assertCondition(responseCount.get() == 1);
        assertCondition("image/png".equals(
            validateImage("boundary.png", MAX_IMAGE_BYTES)));
        assertThrows(
            () -> validateImage("oversize.png", MAX_IMAGE_BYTES + 1),
            "8 MiB");
        assertThrows(
            () -> validateImage("unsupported.gif", 1),
            "JPEG, PNG, or WebP");
        System.out.println("Image payload validation passed.");
    }

    private static void assertCondition(boolean condition) {
        if (!condition) {
            throw new IllegalStateException("Image payload self-test failed.");
        }
    }

    private static void assertThrows(Runnable action, String expectedMessage) {
        try {
            action.run();
        } catch (IllegalArgumentException error) {
            if (error.getMessage().contains(expectedMessage)) {
                return;
            }
            throw error;
        }
        throw new IllegalStateException("Expected validation to fail.");
    }

    private static String requireConfiguration(
        Configuration configuration,
        String name) {
        String value = configuration.get(name);
        if (value == null || value.trim().isEmpty()) {
            throw new IllegalStateException(
                "Set " + name + " before running the sample.");
        }
        return value.trim();
    }
}
