// See https://aka.ms/new-console-template for more information
// Console.WriteLine("Hello, World!");


using System;
using Azure;
using Azure.Core;
using Azure.Identity;
using Azure.ResourceManager;
using Azure.ResourceManager.Resources;
using Azure.ResourceManager.Models;
using Azure.ResourceManager.CognitiveServices;
using Azure.ResourceManager.CognitiveServices.Models;


namespace AiAgentsTests
{

    // This is an app that creates a resource group, a Azure AI Foundry project.
    // It uses the Azure SDK for .NET to interact with Azure resources.
    // <create_project>
    public class CreateRGAzureAI
    {
        public static void CreateRG(string[] args)
        {

            string resourceGroupName = "AzureAIFactoryNET";
            string foundryResourceName = "FoundryProjectNET";

            AzureLocation location = AzureLocation.EastUS;

            var credential = new DefaultAzureCredential();
            var armClient = new ArmClient(credential);

            // Create a resource group and assign roles to it
            ResourceGroupResource resourceGroup = CreateRG(resourceGroupName, location, armClient).Result;

            Console.WriteLine($"Created resource group: {resourceGroup.Data.Name}");
            Console.WriteLine($"Resource group ID: {resourceGroup.Data.Id}");

            // Create a Foundry project
            CreateFoundryAIProject(resourceGroup, foundryResourceName, location).Wait();
        }
        public static async Task<ResourceGroupResource> CreateRG(string resourceGroupName, AzureLocation location, ArmClient armClient)

        {
            SubscriptionResource subscription = await armClient.GetDefaultSubscriptionAsync();
            ResourceGroupCollection resourceGroupCollection = subscription.GetResourceGroups();

            ResourceGroupData resourceGroupData = new ResourceGroupData(location);
            ResourceGroupResource rg = (await resourceGroupCollection.CreateOrUpdateAsync(WaitUntil.Completed, resourceGroupName, resourceGroupData)).Value;

            return rg;
        }

        public static async Task CreateFoundryAIProject(ResourceGroupResource resourceGroupResource, string foundryResourceName, AzureLocation location)
        {
            CognitiveServicesAccountCollection accountCollection = resourceGroupResource.GetCognitiveServicesAccounts();
            
            var parameters = new CognitiveServicesAccountData(location)
            {
                Kind = "AIServices",
                Sku = new CognitiveServicesSku("S0"),
                Identity = new ManagedServiceIdentity(ManagedServiceIdentityType.SystemAssigned),
            };
            
            await accountCollection.CreateOrUpdateAsync(
                WaitUntil.Completed,
                foundryResourceName,
                parameters);
        }
        // </create_project>
    }
}



