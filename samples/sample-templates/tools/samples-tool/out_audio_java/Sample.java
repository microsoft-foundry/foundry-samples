import com.azure.identity.AuthenticationUtil;
import com.openai.client.OpenAIClient;
import com.openai.azure.credential.AzureApiKeyCredential;
import com.openai.client.okhttp.OpenAIOkHttpClient;
import com.openai.credential.BearerTokenCredential;
import com.openai.models.audio.AudioModel;
import com.openai.models.audio.transcriptions.TranscriptionCreateParams;
import com.azure.core.credential.AzureKeyCredential;
import java.nio.file.Path;
import java.nio.file.Paths;

public class Main {
    public static void main(String[] args) {
        
        String endpoint = System.getenv("AZURE_OPENAI_ENDPOINT");
        String azureOpenaiKey = System.getenv("AZURE_OPENAI_API_KEY");
        
        OpenAIOkHttpClient.Builder clientBuilder = OpenAIOkHttpClient.builder();
        clientBuilder
                .baseUrl(endpoint)
                .credential(AzureApiKeyCredential.create(azureOpenaiKey));        
        
        OpenAIClient client = clientBuilder.build();

         // Load the audio file 'batman.wav' from the classpath.
        // Ensure the file is placed in the 'resources' directory of the project.
        ClassLoader classloader = Thread.currentThread().getContextClassLoader();
        Path path = Paths.get(classloader.getResource("batman.wav").toURI());

        TranscriptionCreateParams createParams = TranscriptionCreateParams.builder()
            .file(path)
            .model(AudioModel.of("whisper"))
            .build();

        var result = client.audio()
            .transcriptions()
            .create(createParams)
            .asTranscription();
       
       System.out.println(result.text());
    }
}