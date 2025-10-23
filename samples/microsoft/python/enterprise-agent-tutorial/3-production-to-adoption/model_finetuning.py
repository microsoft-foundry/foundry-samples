"""
Model Fine-Tuning Pipeline Module

This module demonstrates how to prepare training data from production conversations
and create Azure OpenAI fine-tuning jobs to optimize agent performance.

Key Features:
- Training data preparation from feedback
- Azure OpenAI fine-tuning job creation
- Model version management
- A/B testing framework
- Performance comparison
"""

import os
import json
from datetime import datetime
from typing import Dict, List
import random
import helpers

class ModelFineTuning:
    """Handles model fine-tuning pipeline."""
    
    def __init__(self, project_client, agent_id: str):
        """Initialize fine-tuning with project client and agent ID."""
        self.project_client = project_client
        self.agent_id = agent_id
        self.model_name = os.getenv("MODEL_DEPLOYMENT_NAME", "gpt-4o-mini")
    
    # <training_data_prep>
    # NOTE: This code is a non-runnable snippet of the larger sample code from which it is taken.
    def prepare_training_data(self, min_rating: float = 4.0) -> List[Dict]:
        """
        Prepare training data from production conversations.
        
        Filters conversations based on:
        - User feedback ratings
        - Response quality metrics
        - Token length constraints
        
        Args:
            min_rating: Minimum feedback rating to include
            
        Returns:
            List of training examples in OpenAI format
        """
        helpers.print_info("Preparing training data from conversations...")
        
        # Generate synthetic training examples for demonstration
        training_examples = []
        num_examples = random.randint(2000, 2500)
        
        question_templates = [
            "What is our company policy on {}?",
            "How do I configure {} in Azure?",
            "What are the security requirements for {}?",
            "Can you explain how to implement {}?",
            "What's the best practice for {}?"
        ]
        
        topics = [
            "remote work", "multi-factor authentication", "data encryption",
            "conditional access", "SharePoint security", "Azure AD",
            "compliance", "data governance", "collaboration"
        ]
        
        for i in range(num_examples):
            topic = random.choice(topics)
            question = random.choice(question_templates).format(topic)
            
            # Generate response (would come from actual conversations in production)
            response = f"Based on our company policies and Azure best practices, {topic} should be implemented with the following considerations..."
            
            # OpenAI fine-tuning format
            example = {
                "messages": [
                    {"role": "system", "content": "You are a helpful workplace assistant."},
                    {"role": "user", "content": question},
                    {"role": "assistant", "content": response}
                ],
                "metadata": {
                    "conversation_id": f"conv-{i:06d}",
                    "rating": random.uniform(4.0, 5.0),
                    "timestamp": datetime.now().isoformat()
                }
            }
            
            training_examples.append(example)
        
        helpers.print_success(f"Prepared {len(training_examples)} training examples")
        return training_examples
    # </training_data_prep>
    
    def save_training_data(self, training_examples: List[Dict], filename: str = "training_data.jsonl"):
        """Save training data in JSONL format for Azure OpenAI."""
        helpers.print_info(f"Saving training data to {filename}...")
        
        with open(filename, 'w', encoding='utf-8') as f:
            for example in training_examples:
                # Remove metadata for fine-tuning file
                clean_example = {"messages": example["messages"]}
                f.write(json.dumps(clean_example) + '\n')
        
        file_size_mb = os.path.getsize(filename) / (1024 * 1024)
        helpers.print_success(f"Saved {len(training_examples)} examples ({file_size_mb:.2f} MB)")
    
    # <finetuning_job>
    # NOTE: This code is a non-runnable snippet of the larger sample code from which it is taken.
    def create_finetuning_job(self, training_file_path: str) -> Dict:
        """
        Create Azure OpenAI fine-tuning job.
        
        In production, this would:
        1. Upload training file to Azure OpenAI
        2. Create fine-tuning job with hyperparameters
        3. Monitor job progress
        4. Deploy fine-tuned model
        
        Args:
            training_file_path: Path to training data file
            
        Returns:
            Fine-tuning job configuration
        """
        helpers.print_info("Creating fine-tuning job...")
        
        # In production, would use Azure OpenAI API:
        # from openai import AzureOpenAI
        # client = AzureOpenAI(...)
        # job = client.fine_tuning.jobs.create(...)
        
        job_config = {
            "job_id": f"ftjob-{random.randint(100000, 999999)}",
            "base_model": self.model_name,
            "training_file": training_file_path,
            "hyperparameters": {
                "n_epochs": 3,
                "batch_size": "auto",
                "learning_rate_multiplier": "auto"
            },
            "suffix": f"workplace-assistant-v{datetime.now().strftime('%Y%m%d')}",
            "status": "pending",
            "created_at": helpers.format_timestamp(),
            "estimated_completion": "4-6 hours"
        }
        
        helpers.print_success(f"Fine-tuning job created: {job_config['job_id']}")
        helpers.print_info(f"Estimated completion: {job_config['estimated_completion']}")
        
        return job_config
    # </finetuning_job>
    
    def run(self) -> Dict:
        """Execute complete fine-tuning workflow."""
        helpers.print_header("Model Fine-Tuning Pipeline")
        
        # Prepare training data
        training_examples = self.prepare_training_data()
        
        # Save training data
        self.save_training_data(training_examples)
        
        # Create fine-tuning job
        job_config = self.create_finetuning_job("training_data.jsonl")
        
        # Display results
        helpers.print_finetuning_summary({
            "config": {
                "training_examples": len(training_examples),
                "validation_examples": int(len(training_examples) * 0.1),
                "base_model": self.model_name
            },
            "job_id": job_config["job_id"],
            "status": job_config["status"]
        })
        
        # Save results
        result = {
            "training_data_size": len(training_examples),
            "job_configuration": job_config,
            "timestamp": helpers.format_timestamp()
        }
        
        helpers.save_json(result, "finetuning_config.json")
        
        return result

def main():
    """Standalone execution for testing."""
    from dotenv import load_dotenv
    load_dotenv()
    
    class MockProjectClient:
        pass
    
    project_client = MockProjectClient()
    agent_id = os.getenv("AGENT_ID", "agent-test-123")
    
    finetuner = ModelFineTuning(project_client, agent_id)
    finetuner.run()

if __name__ == "__main__":
    main()
