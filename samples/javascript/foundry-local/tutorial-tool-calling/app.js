// <complete_code>
// <imports>
import {
    ChatSession,
    FoundryLocalManager,
    Item,
    Request
} from 'foundry-local-sdk';
import * as readline from 'readline';
// </imports>

// <tool_definitions>
// --- Tool definitions ---
const tools = [
    {
        name: 'get_weather',
        description: 'Get the current weather for a location',
        jsonSchema: JSON.stringify({
            type: 'object',
            properties: {
                location: {
                    type: 'string',
                    description: 'The city or location'
                },
                unit: {
                    type: 'string',
                    enum: ['celsius', 'fahrenheit'],
                    description: 'Temperature unit'
                }
            },
            required: ['location']
        })
    },
    {
        name: 'calculate',
        description: 'Perform a math calculation',
        jsonSchema: JSON.stringify({
            type: 'object',
            properties: {
                expression: {
                    type: 'string',
                    description: 'The math expression to evaluate'
                }
            },
            required: ['expression']
        })
    }
];

// --- Tool implementations ---
function getWeather(location, unit = 'celsius') {
    return {
        location,
        temperature: unit === 'celsius' ? 22 : 72,
        unit,
        condition: 'Sunny'
    };
}

function calculate(expression) {
    // Input is validated against a strict allowlist of numeric/math characters,
    // making this safe from code injection in this tutorial context.
    const allowed = /^[0-9+\-*/(). ]+$/;
    if (!allowed.test(expression)) {
        return { error: 'Invalid expression' };
    }
    try {
        const result = Function(
            `"use strict"; return (${expression})`
        )();
        return { expression, result };
    } catch (err) {
        return { error: err.message };
    }
}

const toolFunctions = {
    get_weather: (args) => getWeather(args.location, args.unit),
    calculate: (args) => calculate(args.expression)
};
// </tool_definitions>

// <tool_loop>
async function processToolCalls(response, chatSession) {
    let currentResponse = response;

    while (currentResponse.finishReason === 'toolCalls') {
        const toolResults = [];
        for (const toolCall of currentResponse.output.filter(
            (item) => item.type === 'toolCall'
        )) {
            const functionName = toolCall.name;
            const args = JSON.parse(toolCall.arguments);
            console.log(
                `  Tool call: ${functionName}` +
                `(${JSON.stringify(args)})`
            );

            const implementation = toolFunctions[functionName];
            const result = implementation
                ? implementation(args)
                : { error: `Unknown tool: ${functionName}` };
            toolResults.push(Item.toolResult(
                toolCall.callId,
                JSON.stringify(result)
            ));
        }
        if (toolResults.length === 0) {
            throw new Error('The model requested tools but returned no tool calls.');
        }

        const followUp = new Request()
            .setOptions({ toolChoice: 'auto' });
        for (const result of toolResults) {
            followUp.addItem(result);
        }
        currentResponse = await chatSession.processRequest(followUp);
    }

    return currentResponse.output
        .map((item) => item.type === 'message'
            ? item.content ?? item.parts?.map((part) => part.text ?? '').join('') ?? ''
            : item.type === 'text' ? item.text : '')
        .join('');
}
// </tool_loop>

// <init>
// --- Main application ---
const manager = FoundryLocalManager.create({
    appName: 'foundry_local_samples',
    logLevel: 'info'
});

// Download and register all execution providers.
let currentEp = '';
await manager.downloadAndRegisterEps((epName, percent) => {
    if (epName !== currentEp) {
        if (currentEp !== '') process.stdout.write('\n');
        currentEp = epName;
    }
    process.stdout.write(`\r  ${epName.padEnd(30)}  ${percent.toFixed(1).padStart(5)}%`);
});
if (currentEp !== '') process.stdout.write('\n');

const model = await manager.catalog.getModel('qwen2.5-0.5b');

await model.download((progress) => {
    process.stdout.write(
        `\rDownloading model: ${progress.toFixed(2)}%`
    );
});
console.log('\nModel downloaded.');

await model.load();
console.log('Model loaded and ready.');

const chatSession = new ChatSession(model);
for (const tool of tools) {
    chatSession.addToolDefinition(tool);
}
let firstTurn = true;

const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout
});

const askQuestion = (prompt) =>
    new Promise((resolve) => {
        if (rl.closed) return resolve('quit');
        const onClose = () => resolve('quit');
        rl.once('close', onClose);
        rl.question(prompt, (answer) => {
            rl.off('close', onClose);
            resolve(answer);
        });
    });

console.log(
    '\nTool-calling assistant ready! Type \'quit\' to exit.\n'
);

while (true) {
    const userInput = await askQuestion('You: ');
    if (
        userInput.trim().toLowerCase() === 'quit' ||
        userInput.trim().toLowerCase() === 'exit'
    ) {
        break;
    }

    const request = new Request().setOptions({ toolChoice: 'auto' });
    if (firstTurn) {
        request.addItem(Item.systemMessage(
            'You are a helpful assistant with access to tools. ' +
            'Use them when needed to answer questions accurately.'
        ));
        firstTurn = false;
    }
    request.addItem(Item.userMessage(userInput));

    const response = await chatSession.processRequest(request);
    const answer = await processToolCalls(
        response, chatSession
    );

    console.log(`Assistant: ${answer}\n`);
}

chatSession.dispose();
await model.unload();
console.log('Model unloaded. Goodbye!');
rl.close();
// </init>
// </complete_code>
