using System.ComponentModel.DataAnnotations;

namespace a2a_notification_service.Models
{
    public class A2ATask
    {
        [Required]
        public string? AgentId { get; set; }
        [Required]
        public bool IsFinal { get; set; }
        public string? Message { get; set; } = null;
    }
}
