#!/usr/bin/env python3
"""
Generate architecture diagrams for Azure AI Foundry VNet deployment layers.
Clean, uniform Azure-inspired style with consistent colors.
"""

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

# Very light green/yellow pastel color scheme (much lighter backgrounds)
COLORS = {
    # Primary colors
    'primary': '#8BC34A',        # Light lime green
    'primary_dark': '#4A5D23',   # Olive (for headers)
    'primary_light': '#C5E1A5',  # Pale lime
    
    # Background colors (extremely light, almost white)
    'bg_light': '#FEFFFE',       # Almost pure white
    'bg_medium': '#FCFEF8',      # Barely tinted white  
    'bg_dark': '#F8FCF2',        # Very subtle green tint
    
    # Accent 
    'accent': '#689F38',         # Lime accent
    'highlight': '#FFFEF5',      # Very light cream highlight
    
    # Neutrals
    'white': '#FFFFFF',          # Pure white
    'text_dark': '#4A5D23',      # Olive text
    'text_light': '#FFFFFF',
    'border': '#D4E6A5',         # Pale yellow-green border
    'border_light': '#E8F2D0',   # Very light lime border
}


def setup_figure(title, figsize=(14, 8)):
    """Create a figure with consistent styling."""
    fig, ax = plt.subplots(1, 1, figsize=figsize)
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 8)
    ax.set_aspect('equal')
    ax.axis('off')
    fig.patch.set_facecolor(COLORS['white'])
    ax.set_facecolor(COLORS['white'])
    
    # Title with consistent styling
    ax.text(7, 7.7, title, ha='center', va='center',
            fontsize=16, fontweight='bold', color=COLORS['primary_dark'])
    return fig, ax


def draw_box(ax, x, y, w, h, fill_color, border_color, border_width=2):
    """Draw a rounded box."""
    box = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.02,rounding_size=0.15",
        facecolor=fill_color,
        edgecolor=border_color,
        linewidth=border_width
    )
    ax.add_patch(box)
    return box


# =============================================================================
# LAYER 1: Network Foundation
# =============================================================================
def generate_layer1():
    fig, ax = setup_figure('Layer 1: Network Foundation', figsize=(14, 9))
    
    # Main VNet container
    draw_box(ax, 0.5, 1, 13, 6.2, COLORS['bg_light'], COLORS['primary'], 3)
    ax.text(7, 6.9, 'Virtual Network', ha='center', va='center',
            fontsize=14, fontweight='bold', color=COLORS['primary_dark'])
    ax.text(7, 6.5, '192.168.0.0/16', ha='center', va='center',
            fontsize=10, color=COLORS['primary'], family='monospace')
    
    # Agent Subnet
    draw_box(ax, 1, 4, 3.8, 2.2, COLORS['bg_medium'], COLORS['primary'], 2)
    ax.text(2.9, 5.8, 'Agent Subnet', ha='center', va='center',
            fontsize=11, fontweight='bold', color=COLORS['primary_dark'])
    ax.text(2.9, 5.4, '192.168.0.0/24', ha='center', va='center',
            fontsize=9, color=COLORS['primary'], family='monospace')
    ax.text(2.9, 4.85, 'Delegated to', ha='center', va='center',
            fontsize=9, color=COLORS['text_dark'])
    ax.text(2.9, 4.5, 'Microsoft.App/environments', ha='center', va='center',
            fontsize=8, color=COLORS['primary'], fontweight='bold')
    ax.text(2.9, 4.15, '(Agent Runtime)', ha='center', va='center',
            fontsize=8, color=COLORS['accent'], style='italic')
    
    # Private Endpoint Subnet
    draw_box(ax, 5.1, 4, 3.8, 2.2, COLORS['bg_medium'], COLORS['primary'], 2)
    ax.text(7, 5.8, 'Private Endpoint Subnet', ha='center', va='center',
            fontsize=11, fontweight='bold', color=COLORS['primary_dark'])
    ax.text(7, 5.4, '192.168.1.0/24', ha='center', va='center',
            fontsize=9, color=COLORS['primary'], family='monospace')
    ax.text(7, 4.85, 'Hosts Private Endpoints', ha='center', va='center',
            fontsize=9, color=COLORS['text_dark'])
    ax.text(7, 4.5, 'for all Azure Services', ha='center', va='center',
            fontsize=9, color=COLORS['text_dark'])
    
    # MCP Subnet
    draw_box(ax, 9.2, 4, 3.8, 2.2, COLORS['bg_medium'], COLORS['primary'], 2)
    ax.text(11.1, 5.8, 'MCP Subnet', ha='center', va='center',
            fontsize=11, fontweight='bold', color=COLORS['primary_dark'])
    ax.text(11.1, 5.4, '192.168.2.0/24', ha='center', va='center',
            fontsize=9, color=COLORS['primary'], family='monospace')
    ax.text(11.1, 4.85, 'User-deployed', ha='center', va='center',
            fontsize=9, color=COLORS['text_dark'])
    ax.text(11.1, 4.5, 'Container Apps (MCP)', ha='center', va='center',
            fontsize=9, color=COLORS['text_dark'])
    
    # Key points box
    draw_box(ax, 1, 1.3, 12, 2.4, COLORS['white'], COLORS['border_light'], 1.5)
    ax.text(7, 3.4, 'KEY POINTS', ha='center', va='center',
            fontsize=10, fontweight='bold', color=COLORS['primary_dark'])
    
    key_points = [
        '• BYO VNet approach - full control over network topology',
        '• Agent subnet MUST be delegated to Microsoft.App/environments',
        '• Private endpoints ensure zero public internet exposure',
        '• All subnets should be /24 or larger for capacity'
    ]
    for i, point in enumerate(key_points):
        ax.text(7, 3.0 - i*0.4, point, ha='center', va='center',
                fontsize=9, color=COLORS['text_dark'])
    
    plt.tight_layout()
    plt.savefig('layer1_network_foundation.png', dpi=150, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    plt.close()
    print("Generated layer1_network_foundation.png")


# =============================================================================
# LAYER 2: Data Resources (BYO)
# =============================================================================
def generate_layer2():
    fig, ax = setup_figure('Layer 2: BYO Data Resources', figsize=(14, 9))
    
    # Header banner
    draw_box(ax, 0.5, 6.2, 13, 1, COLORS['bg_light'], COLORS['primary'], 2)
    ax.text(7, 6.7, '"Bring Your Own" Resources - Customer-Owned Data Storage', ha='center', va='center',
            fontsize=12, fontweight='bold', color=COLORS['primary_dark'])
    
    # Cosmos DB Box
    draw_box(ax, 1, 3.2, 3.8, 2.7, COLORS['primary'], COLORS['primary_dark'], 2)
    ax.text(2.9, 5.5, 'Azure Cosmos DB', ha='center', va='center',
            fontsize=12, fontweight='bold', color=COLORS['text_light'])
    ax.text(2.9, 5.0, '─────────────', ha='center', va='center',
            fontsize=10, color=COLORS['primary_light'])
    ax.text(2.9, 4.6, 'Thread Storage', ha='center', va='center',
            fontsize=10, color=COLORS['bg_light'])
    ax.text(2.9, 4.1, '• Conversation history', ha='center', va='center',
            fontsize=9, color=COLORS['bg_medium'])
    ax.text(2.9, 3.7, '• Agent state persistence', ha='center', va='center',
            fontsize=9, color=COLORS['bg_medium'])
    
    # Storage Account Box
    draw_box(ax, 5.1, 3.2, 3.8, 2.7, COLORS['primary'], COLORS['primary_dark'], 2)
    ax.text(7, 5.5, 'Azure Storage', ha='center', va='center',
            fontsize=12, fontweight='bold', color=COLORS['text_light'])
    ax.text(7, 5.0, '─────────────', ha='center', va='center',
            fontsize=10, color=COLORS['primary_light'])
    ax.text(7, 4.6, 'File Storage', ha='center', va='center',
            fontsize=10, color=COLORS['bg_light'])
    ax.text(7, 4.1, '• Uploaded documents', ha='center', va='center',
            fontsize=9, color=COLORS['bg_medium'])
    ax.text(7, 3.7, '• Agent file attachments', ha='center', va='center',
            fontsize=9, color=COLORS['bg_medium'])
    
    # AI Search Box
    draw_box(ax, 9.2, 3.2, 3.8, 2.7, COLORS['primary'], COLORS['primary_dark'], 2)
    ax.text(11.1, 5.5, 'Azure AI Search', ha='center', va='center',
            fontsize=12, fontweight='bold', color=COLORS['text_light'])
    ax.text(11.1, 5.0, '─────────────', ha='center', va='center',
            fontsize=10, color=COLORS['primary_light'])
    ax.text(11.1, 4.6, 'Vector Store', ha='center', va='center',
            fontsize=10, color=COLORS['bg_light'])
    ax.text(11.1, 4.1, '• RAG embeddings', ha='center', va='center',
            fontsize=9, color=COLORS['bg_medium'])
    ax.text(11.1, 3.7, '• Semantic search index', ha='center', va='center',
            fontsize=9, color=COLORS['bg_medium'])
    
    # Security configuration box
    draw_box(ax, 1, 1.2, 12, 1.7, COLORS['bg_light'], COLORS['primary'], 1.5)
    ax.text(7, 2.6, 'SECURITY CONFIGURATION (All Resources)', ha='center', va='center',
            fontsize=10, fontweight='bold', color=COLORS['primary_dark'])
    ax.text(7, 2.1, 'Public network access: DISABLED  |  Authentication: Azure AD only  |  TLS: 1.2 minimum', 
            ha='center', va='center', fontsize=9, color=COLORS['text_dark'], family='monospace')
    ax.text(7, 1.6, 'Network ACLs: Deny by default  |  Shared keys: DISABLED', 
            ha='center', va='center', fontsize=9, color=COLORS['text_dark'], family='monospace')
    
    plt.tight_layout()
    plt.savefig('layer2_data_resources.png', dpi=150, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    plt.close()
    print("Generated layer2_data_resources.png")


# =============================================================================
# LAYER 3: AI Services
# =============================================================================
def generate_layer3():
    fig, ax = setup_figure('Layer 3: AI Services Account & Model', figsize=(14, 9))
    
    # Main AI Services container
    draw_box(ax, 1, 2, 12, 5.3, COLORS['bg_light'], COLORS['primary'], 3)
    ax.text(7, 7, 'Azure AI Services Account', ha='center', va='center',
            fontsize=14, fontweight='bold', color=COLORS['primary_dark'])
    ax.text(7, 6.55, 'Microsoft.CognitiveServices/accounts (Kind: AIServices)', ha='center', va='center',
            fontsize=9, color=COLORS['primary'], family='monospace')
    
    # Account properties box
    draw_box(ax, 1.5, 4.3, 5, 2.1, COLORS['white'], COLORS['border_light'], 1.5)
    ax.text(4, 6.1, 'Account Properties', ha='center', va='center',
            fontsize=10, fontweight='bold', color=COLORS['primary_dark'])
    
    props = ['SKU: S0', 'Identity: System-Assigned MSI', 'Public Access: Disabled', 
             'Network: Custom VNet Binding', 'Custom Subdomain: Enabled']
    for i, prop in enumerate(props):
        ax.text(4, 5.65 - i*0.3, prop, ha='center', va='center',
                fontsize=9, color=COLORS['text_dark'], family='monospace')
    
    # Model Deployment box
    draw_box(ax, 7.5, 4.3, 5, 2.1, COLORS['primary'], COLORS['primary_dark'], 2)
    ax.text(10, 6.1, 'Model Deployment', ha='center', va='center',
            fontsize=10, fontweight='bold', color=COLORS['text_light'])
    
    model_props = ['Model: GPT-4o', 'Format: OpenAI', 'Version: 2024-11-20', 
                   'SKU: GlobalStandard', 'Capacity: 30K TPM']
    for i, prop in enumerate(model_props):
        ax.text(10, 5.65 - i*0.3, prop, ha='center', va='center',
                fontsize=9, color=COLORS['bg_light'], family='monospace')
    
    # Network binding box
    draw_box(ax, 2.5, 2.3, 9, 1.5, COLORS['bg_medium'], COLORS['primary'], 1.5)
    ax.text(7, 3.5, 'Network Binding', ha='center', va='center',
            fontsize=10, fontweight='bold', color=COLORS['primary_dark'])
    ax.text(7, 3.0, 'agentSubnetId -> Linked to Agent Subnet for secure runtime execution', ha='center', va='center',
            fontsize=9, color=COLORS['text_dark'])
    ax.text(7, 2.6, '(From Layer 1: VNet Agent Subnet)', ha='center', va='center',
            fontsize=9, color=COLORS['primary'], style='italic')
    
    plt.tight_layout()
    plt.savefig('layer3_ai_services.png', dpi=150, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    plt.close()
    print("Generated layer3_ai_services.png")


# =============================================================================
# LAYER 4: Project + Connections
# =============================================================================
def generate_layer4():
    fig, ax = setup_figure('Layer 4: Project & Service Connections', figsize=(14, 10))
    
    # Parent account container (dashed)
    parent = FancyBboxPatch(
        (0.5, 1), 13, 6.3,
        boxstyle="round,pad=0.02,rounding_size=0.15",
        facecolor=COLORS['bg_light'],
        edgecolor=COLORS['border_light'],
        linewidth=2,
        linestyle='--'
    )
    ax.add_patch(parent)
    ax.text(7, 7.1, 'AI Services Account (Parent)', ha='center', va='center',
            fontsize=10, color=COLORS['primary'], style='italic')
    
    # Project box
    draw_box(ax, 1, 1.5, 12, 5.3, COLORS['primary'], COLORS['primary_dark'], 3)
    ax.text(7, 6.5, 'FOUNDRY PROJECT', ha='center', va='center',
            fontsize=14, fontweight='bold', color=COLORS['text_light'])
    ax.text(7, 6.1, 'Microsoft.CognitiveServices/accounts/projects', ha='center', va='center',
            fontsize=9, color=COLORS['bg_light'], family='monospace')
    
    # Identity box
    draw_box(ax, 1.5, 5, 3, 0.9, COLORS['white'], COLORS['border_light'], 1.5)
    ax.text(3, 5.6, 'Identity (MSI)', ha='center', va='center',
            fontsize=9, fontweight='bold', color=COLORS['primary_dark'])
    ax.text(3, 5.25, 'System-Assigned', ha='center', va='center',
            fontsize=8, color=COLORS['text_dark'])
    
    # Connections header
    ax.text(7, 4.6, '-- Service Connections (AAD Auth) --', ha='center', va='center',
            fontsize=11, fontweight='bold', color=COLORS['text_light'])
    
    # Connection boxes
    conn_y = 3.0
    conn_h = 1.2
    
    # Cosmos Connection
    draw_box(ax, 1.5, conn_y, 3.5, conn_h, COLORS['bg_medium'], COLORS['text_light'], 1.5)
    ax.text(3.25, conn_y + 0.85, 'CosmosDB Connection', ha='center', va='center',
            fontsize=9, fontweight='bold', color=COLORS['primary_dark'])
    ax.text(3.25, conn_y + 0.4, 'category: CosmosDB', ha='center', va='center',
            fontsize=8, color=COLORS['text_dark'], family='monospace')
    
    # Storage Connection
    draw_box(ax, 5.25, conn_y, 3.5, conn_h, COLORS['bg_medium'], COLORS['text_light'], 1.5)
    ax.text(7, conn_y + 0.85, 'Storage Connection', ha='center', va='center',
            fontsize=9, fontweight='bold', color=COLORS['primary_dark'])
    ax.text(7, conn_y + 0.4, 'category: AzureStorage', ha='center', va='center',
            fontsize=8, color=COLORS['text_dark'], family='monospace')
    
    # AI Search Connection
    draw_box(ax, 9, conn_y, 3.5, conn_h, COLORS['bg_medium'], COLORS['text_light'], 1.5)
    ax.text(10.75, conn_y + 0.85, 'AI Search Connection', ha='center', va='center',
            fontsize=9, fontweight='bold', color=COLORS['primary_dark'])
    ax.text(10.75, conn_y + 0.4, 'category: CognitiveSearch', ha='center', va='center',
            fontsize=8, color=COLORS['text_dark'], family='monospace')
    
    # Key insight box
    draw_box(ax, 1.5, 1.7, 11, 0.9, COLORS['white'], COLORS['highlight'], 2)
    ax.text(7, 2.15, 'KEY INSIGHT: Connections store target endpoints + auth method.', ha='center', va='center',
            fontsize=9, fontweight='bold', color=COLORS['primary_dark'])
    
    plt.tight_layout()
    plt.savefig('layer4_project_connections.png', dpi=150, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    plt.close()
    print("Generated layer4_project_connections.png")


# =============================================================================
# LAYER 5: Capability Host
# =============================================================================
def generate_layer5():
    fig, ax = setup_figure('Layer 5: Capability Host - The Activator', figsize=(14, 10))
    
    # Main capability host box
    draw_box(ax, 0.5, 2.8, 13, 4.5, COLORS['primary'], COLORS['primary_dark'], 3)
    ax.text(7, 7, 'PROJECT CAPABILITY HOST', ha='center', va='center',
            fontsize=16, fontweight='bold', color=COLORS['text_light'])
    ax.text(7, 6.55, 'Microsoft.CognitiveServices/accounts/projects/capabilityHosts', ha='center', va='center',
            fontsize=9, color=COLORS['bg_light'], family='monospace')
    
    # capabilityHostKind box
    draw_box(ax, 1, 5.5, 3.5, 1, COLORS['white'], COLORS['border_light'], 2)
    ax.text(2.75, 6.15, 'capabilityHostKind', ha='center', va='center',
            fontsize=9, fontweight='bold', color=COLORS['primary_dark'])
    ax.text(2.75, 5.75, '"Agents"', ha='center', va='center',
            fontsize=11, fontweight='bold', color=COLORS['primary'], family='monospace')
    
    # Connection bindings header
    ax.text(7, 5.1, '-- Connection Bindings --', ha='center', va='center',
            fontsize=11, fontweight='bold', color=COLORS['text_light'])
    
    bind_y = 3.9
    bind_h = 0.9
    
    # Vector Store Connections
    draw_box(ax, 1, bind_y, 3.8, bind_h, COLORS['bg_medium'], COLORS['text_light'], 1.5)
    ax.text(2.9, bind_y + 0.6, 'vectorStoreConnections', ha='center', va='center',
            fontsize=8, fontweight='bold', color=COLORS['primary_dark'], family='monospace')
    ax.text(2.9, bind_y + 0.25, '-> AI Search', ha='center', va='center',
            fontsize=9, color=COLORS['text_dark'])
    
    # Storage Connections
    draw_box(ax, 5.1, bind_y, 3.8, bind_h, COLORS['bg_medium'], COLORS['text_light'], 1.5)
    ax.text(7, bind_y + 0.6, 'storageConnections', ha='center', va='center',
            fontsize=8, fontweight='bold', color=COLORS['primary_dark'], family='monospace')
    ax.text(7, bind_y + 0.25, '-> Azure Storage', ha='center', va='center',
            fontsize=9, color=COLORS['text_dark'])
    
    # Thread Storage Connections
    draw_box(ax, 9.2, bind_y, 3.8, bind_h, COLORS['bg_medium'], COLORS['text_light'], 1.5)
    ax.text(11.1, bind_y + 0.6, 'threadStorageConnections', ha='center', va='center',
            fontsize=8, fontweight='bold', color=COLORS['primary_dark'], family='monospace')
    ax.text(11.1, bind_y + 0.25, '-> Cosmos DB', ha='center', va='center',
            fontsize=9, color=COLORS['text_dark'])
    
    # Runtime info box
    draw_box(ax, 1, 3, 12, 0.7, COLORS['bg_light'], COLORS['text_light'], 1.5)
    ax.text(7, 3.35, 'RUNTIME: Creates Container App environment in Agent Subnet | Provisions infrastructure', 
            ha='center', va='center', fontsize=9, fontweight='bold', color=COLORS['primary_dark'])
    
    # Header injection explanation box
    draw_box(ax, 0.5, 0.5, 13, 2.1, COLORS['bg_light'], COLORS['primary'], 2)
    ax.text(7, 2.3, 'HOW CAPABILITY HOST ENABLES ADDITIONAL HEADERS', ha='center', va='center',
            fontsize=11, fontweight='bold', color=COLORS['primary_dark'])
    
    flow_text = [
        '1. Agent makes API call -> 2. Capability Host intercepts -> 3. Looks up connection config',
        '4. Injects headers: Authorization (Bearer token from MSI), x-ms-documentdb-partitionkey, etc.',
        '5. Routes through Private Endpoint -> 6. Resource receives authenticated request'
    ]
    for i, line in enumerate(flow_text):
        ax.text(7, 1.85 - i*0.4, line, ha='center', va='center',
                fontsize=9, color=COLORS['text_dark'], family='monospace')
    
    plt.tight_layout()
    plt.savefig('layer5_capability_host.png', dpi=150, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    plt.close()
    print("Generated layer5_capability_host.png")


# =============================================================================
# DEPLOYMENT FLOW - All Phases (Two Column Layout)
# =============================================================================
def generate_deployment_flow():
    fig, ax = plt.subplots(1, 1, figsize=(32, 18))
    ax.set_xlim(0, 28)
    ax.set_ylim(0, 13)
    ax.set_aspect('equal')
    ax.axis('off')
    fig.patch.set_facecolor(COLORS['white'])
    ax.set_facecolor(COLORS['white'])
    
    # Left column phases (1-4)
    left_phases = [
        {
            'num': '1',
            'title': 'Network Infrastructure',
            'y': 10.0,
            'items': ['VNet + Agent Subnet + PE Subnet + MCP Subnet']
        },
        {
            'num': '2', 
            'title': 'AI Services Account + Model',
            'y': 7.2,
            'items': ['AI Services (Kind: AIServices)', 'Model Deployment (GPT-4o)']
        },
        {
            'num': '3',
            'title': 'BYO Data Resources',
            'y': 4.4,
            'items': ['Cosmos DB (threads)', 'Storage (files)', 'AI Search (vector store)']
        },
        {
            'num': '4',
            'title': 'Private Network Security',
            'y': 1.6,
            'items': ['Private Endpoints for all services', 'Private DNS Zones']
        }
    ]
    
    # Right column phases (5-8)
    right_phases = [
        {
            'num': '5',
            'title': 'Project + Connections',
            'y': 10.0,
            'items': ['Foundry Project', 'CosmosDB / Storage / AI Search', 'connections (AAD Auth)']
        },
        {
            'num': '6',
            'title': 'RBAC (Pre-Capability Host)',
            'y': 7.2,
            'items': ['Storage Blob Data Contributor', 'Cosmos DB Operator', 'Search Index Data Contributor']
        },
        {
            'num': '7',
            'title': 'Capability Host',
            'y': 4.4,
            'items': ['vectorStoreConnections', 'storageConnections', 'threadStorageConnections']
        },
        {
            'num': '8',
            'title': 'RBAC (Post-Capability Host)',
            'y': 1.6,
            'items': ['Storage Blob Data Owner', 'Cosmos Built-In Data Contributor', '(on containers created by caphost)']
        }
    ]
    
    box_width = 12.5
    box_height = 2.4
    left_x = 0.8
    right_x = 14.5
    
    def draw_phase(phase, box_x, y):
        # Main phase box
        box = FancyBboxPatch(
            (box_x, y), box_width, box_height,
            boxstyle="round,pad=0.02,rounding_size=0.15",
            facecolor=COLORS['bg_medium'],
            edgecolor=COLORS['border'],
            linewidth=4
        )
        ax.add_patch(box)
        
        # Phase number circle
        circle = FancyBboxPatch(
            (box_x + 0.3, y + box_height/2 - 0.5), 1.0, 1.0,
            boxstyle="round,pad=0.02,rounding_size=0.5",
            facecolor=COLORS['primary'],
            edgecolor=COLORS['primary_dark'],
            linewidth=3
        )
        ax.add_patch(circle)
        ax.text(box_x + 0.8, y + box_height/2, phase['num'], ha='center', va='center',
                fontsize=36, fontweight='bold', color=COLORS['text_light'])
        
        # Phase title
        ax.text(box_x + 1.6, y + box_height - 0.45, f"Phase {phase['num']}", ha='left', va='center',
                fontsize=26, color=COLORS['accent'], fontweight='bold')
        ax.text(box_x + 4.0, y + box_height - 0.45, f"({phase['title']})", ha='left', va='center',
                fontsize=26, fontweight='bold', color=COLORS['primary_dark'])
        
        # Items - each on its own line
        for j, item in enumerate(phase['items']):
            ax.text(box_x + 1.6, y + box_height - 1.0 - j*0.5, f"• {item}", ha='left', va='center',
                    fontsize=22, color=COLORS['text_dark'])
    
    # Draw left column
    for i, phase in enumerate(left_phases):
        draw_phase(phase, left_x, phase['y'])
        # Arrow to next phase (except last in column)
        if i < len(left_phases) - 1:
            arrow_y = phase['y'] - 0.2
            ax.annotate('', xy=(left_x + box_width/2, arrow_y - 0.35), 
                        xytext=(left_x + box_width/2, arrow_y + 0.05),
                        arrowprops=dict(arrowstyle='->', color=COLORS['primary'], lw=4))
    
    # Draw right column
    for i, phase in enumerate(right_phases):
        draw_phase(phase, right_x, phase['y'])
        # Arrow to next phase (except last in column)
        if i < len(right_phases) - 1:
            arrow_y = phase['y'] - 0.2
            ax.annotate('', xy=(right_x + box_width/2, arrow_y - 0.35), 
                        xytext=(right_x + box_width/2, arrow_y + 0.05),
                        arrowprops=dict(arrowstyle='->', color=COLORS['primary'], lw=4))
    
    plt.tight_layout()
    plt.savefig('deployment_flow.png', dpi=400, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    plt.close()
    print("Generated deployment_flow.png")


# =============================================================================
# Main
# =============================================================================
if __name__ == '__main__':
    print("Generating architecture diagrams...")
    print("-" * 40)
    generate_layer1()
    generate_layer2()
    generate_layer3()
    generate_layer4()
    generate_layer5()
    generate_deployment_flow()
    print("-" * 40)
    print("All diagrams generated successfully!")
