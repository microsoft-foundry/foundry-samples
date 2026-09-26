// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

package com.azure.ai.agents.voice;

import com.azure.ai.agents.AgentsAsyncClient;
import com.azure.ai.agents.AgentsClient;
import com.azure.ai.agents.models.VoiceAgentAudioConfiguration;
import com.azure.ai.agents.models.VoiceAgentAudioOutputConfiguration;
import com.azure.ai.agents.models.VoiceAgentDefinition;
import com.azure.ai.agents.models.VoiceModelType;
import com.azure.ai.agents.models.VoiceOutputModality;
import com.azure.ai.agents.models.VoiceType;
import com.azure.core.exception.ResourceNotFoundException;
import reactor.core.publisher.Mono;

import java.util.Collections;

final class VoiceAgentSampleUtils {
    private VoiceAgentSampleUtils() {
    }

    static VoiceAgentDefinition createDefinition(VoiceModelType modelType, String model, String instructions) {
        VoiceAgentAudioOutputConfiguration output = new VoiceAgentAudioOutputConfiguration()
            .setVoice("en-US-AvaNeural")
            .setVoiceType(VoiceType.AZURE_STANDARD);
        return new VoiceAgentDefinition()
            .setModelType(modelType)
            .setModel(model)
            .setInstructions(instructions)
            .setAudio(new VoiceAgentAudioConfiguration().setOutput(output))
            .setOutputModalities(Collections.singletonList(VoiceOutputModality.AUDIO))
            .setStore(true);
    }

    static void requireUnusedAgentName(AgentsClient client, String agentName) {
        try {
            client.getAgent(agentName);
        } catch (ResourceNotFoundException ignored) {
            return;
        }
        throw new IllegalArgumentException("Agent already exists; use a disposable FOUNDRY_VOICE_AGENT_NAME: "
            + agentName);
    }

    static Mono<Void> requireUnusedAgentName(AgentsAsyncClient client, String agentName) {
        return client.getAgent(agentName)
            .flatMap(agent -> Mono.<Void>error(new IllegalArgumentException(
                "Agent already exists; use a disposable FOUNDRY_VOICE_AGENT_NAME: " + agentName)))
            .onErrorResume(ResourceNotFoundException.class, ignored -> Mono.empty());
    }
}
