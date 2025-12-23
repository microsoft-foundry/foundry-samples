using System.ComponentModel.DataAnnotations;

namespace a2a_notification_service.Models
{
    public class UserMessageModel
    {
        [Required]
        public string? Message { get; set; }
        [Required]
        public string? AgentId { get; set; }
    }
}
