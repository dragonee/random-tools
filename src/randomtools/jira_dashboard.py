"""Search Jira dashboards and list dashboard gadgets to find gadget IDs.

Usage:
    jira-dashboard [<dashboard_id>] [--filter=<type>] [--search=<query>] [--raw] [--properties=<gadget_id>] [--config=<gadget_id>]
    jira-dashboard (-h | --help)

Options:
    -h --help                Show this screen.
    --filter=<type>          Filter by gadget type (e.g., "TimeTrackingGadget").
    --search=<query>         Search dashboards by name/description.
    --raw                    Show raw JSON response.
    --properties=<gadget_id> Show properties for specific gadget ID.
    --config=<gadget_id>     Show gadgetConfig property value for specific gadget ID.

Examples:
    jira-dashboard                                 # List all available dashboards
    jira-dashboard 12345                           # List all gadgets in dashboard 12345
    jira-dashboard 12345 --filter=TimeTrackingGadget  # Filter time tracking gadgets
    jira-dashboard --search="My Dashboard"         # Search for dashboards by name
    jira-dashboard 12345 --raw                     # Show raw JSON response
    jira-dashboard 12345 --properties=11579       # Show properties for gadget 11579
    jira-dashboard 12345 --config=11579           # Show gadgetConfig for gadget 11579

Configuration:
    Create ~/.jira/config.ini with:
    [Jira]
    domain = your-domain
    email = your-email@example.com
    api_token = your-api-token

"""
import json
import requests
from requests.auth import HTTPBasicAuth
from docopt import docopt
from randomtools.config.jira import JiraConfigFile

VERSION = '1.0'


def list_dashboards(config, search_query=None):
    """List available Jira dashboards."""
    url = f"{config.base_url}/rest/api/3/dashboard"
    
    auth = HTTPBasicAuth(config.email, config.api_token)
    
    headers = {
        "Accept": "application/json"
    }
    
    print("Fetching available dashboards...")
    
    try:
        response = requests.get(
            url,
            headers=headers,
            auth=auth
        )
        
        if response.status_code == 200:
            data = response.json()
            dashboards = data.get('dashboards', [])
            
            # Filter by search query if provided
            if search_query:
                search_lower = search_query.lower()
                dashboards = [d for d in dashboards 
                            if search_lower in d.get('name', '').lower() 
                            or search_lower in d.get('description', '').lower()]
                print(f"Dashboards matching '{search_query}': {len(dashboards)}")
            else:
                print(f"Total dashboards found: {len(dashboards)}")
            
            print("=" * 80)
            
            if not dashboards:
                print("No dashboards found")
                return True
            
            for dashboard in dashboards:
                print(f"ID: {dashboard.get('id', 'N/A')}")
                print(f"Name: {dashboard.get('name', 'N/A')}")
                
                description = dashboard.get('description')
                if description:
                    print(f"Description: {description}")
                
                # Show owner info
                owner = dashboard.get('owner')
                if owner:
                    print(f"Owner: {owner.get('displayName', 'N/A')}")
                
                # Show view URL
                view_url = dashboard.get('view')
                if view_url:
                    print(f"View URL: {view_url}")
                
                print("-" * 40)
            
            print(f"\nTo view items in a dashboard, run:")
            print(f"jira-dashboard <dashboard_id>")
            
            return True
            
        else:
            print(f"✗ Failed to fetch dashboards. Status: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"✗ Error connecting to Jira API: {e}")
        return False


def get_gadget_properties(config, dashboard_id, gadget_id, show_raw=False):
    """Get properties for a specific gadget."""
    url = f"{config.base_url}/rest/api/3/dashboard/{dashboard_id}/items/{gadget_id}/properties"
    
    auth = HTTPBasicAuth(config.email, config.api_token)
    
    headers = {
        "Accept": "application/json"
    }
    
    print(f"Fetching properties for gadget {gadget_id} in dashboard {dashboard_id}...")
    
    try:
        response = requests.get(
            url,
            headers=headers,
            auth=auth
        )
        
        if response.status_code == 200:
            data = response.json()
            if show_raw:
                print("Raw response:")
                print(json.dumps(data, indent=2))
                print("-" * 80)
            
            keys = data.get('keys', [])
            
            if keys:
                print(f"Properties for gadget {gadget_id}:")
                print("-" * 40)
                for key_info in keys:
                    print(f"Key: {key_info.get('key', 'N/A')}")
                    print(f"Self URL: {key_info.get('self', 'N/A')}")
                    print("-" * 20)
            else:
                print(f"No properties found for gadget {gadget_id}")
            
            return True
            
        elif response.status_code == 404:
            print(f"✗ Gadget {gadget_id} not found in dashboard {dashboard_id}")
            return False
        elif response.status_code == 403:
            print("✗ Access denied. Check your permissions for this dashboard/gadget")
            return False
        else:
            print(f"✗ Failed to fetch gadget properties. Status: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"✗ Error connecting to Jira API: {e}")
        return False


def get_gadget_config(config, dashboard_id, gadget_id, show_raw=False):
    """Get gadgetConfig property value for a specific gadget."""
    url = f"{config.base_url}/rest/api/3/dashboard/{dashboard_id}/items/{gadget_id}/properties/gadgetConfig"
    
    auth = HTTPBasicAuth(config.email, config.api_token)
    
    headers = {
        "Accept": "application/json"
    }
    
    print(f"Fetching gadgetConfig for gadget {gadget_id} in dashboard {dashboard_id}...")
    
    try:
        response = requests.get(
            url,
            headers=headers,
            auth=auth
        )
        
        if response.status_code == 200:
            data = response.json()
            if show_raw:
                print("Raw response:")
                print(json.dumps(data, indent=2))
                print("-" * 80)
            
            key = data.get('key', 'N/A')
            value = data.get('value', {})
            
            print(f"Config for gadget {gadget_id}:")
            print(f"Property Key: {key}")
            print("-" * 40)
            
            if value:
                print("Configuration:")
                for config_key, config_value in value.items():
                    print(f"  {config_key}: {config_value}")
            else:
                print("No configuration data found")
            
            return True
            
        elif response.status_code == 404:
            print(f"✗ gadgetConfig property not found for gadget {gadget_id} in dashboard {dashboard_id}")
            return False
        elif response.status_code == 403:
            print("✗ Access denied. Check your permissions for this dashboard/gadget")
            return False
        else:
            print(f"✗ Failed to fetch gadget config. Status: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"✗ Error connecting to Jira API: {e}")
        return False


def list_dashboard_items(config, dashboard_id, filter_type=None, show_raw=False):
    """List all gadgets in a Jira dashboard."""
    url = f"{config.base_url}/rest/api/3/dashboard/{dashboard_id}/gadget"
    
    auth = HTTPBasicAuth(config.email, config.api_token)
    
    headers = {
        "Accept": "application/json"
    }
    
    print(f"Fetching dashboard gadgets for dashboard {dashboard_id}...")
    
    try:
        response = requests.get(
            url,
            headers=headers,
            auth=auth
        )
        
        if response.status_code == 200:
            data = response.json()
            if show_raw:
                print("Raw response:")
                print(json.dumps(data, indent=2))
                print("-" * 80)
            
            gadgets = data.get('gadgets', [])
            
            filtered_gadgets = []
            for gadget in gadgets:
                if filter_type:
                    filter_lower = filter_type.lower()
                    title = gadget.get('title', '').lower()
                    module_key = gadget.get('moduleKey', '').lower()
                    uri = gadget.get('uri', '').lower()
                    
                    if (filter_lower not in title and 
                        filter_lower not in module_key and 
                        filter_lower not in uri):
                        continue
                filtered_gadgets.append(gadget)
            
            if not filter_type:
                print(f"Total gadgets: {len(gadgets)}")
                print("-" * 80)
            
            for gadget in filtered_gadgets:
                print(f"Gadget ID: {gadget.get('id', 'N/A')}")
                print(f"Dashboard ID: {dashboard_id}")
                
                position = gadget.get('position', {})
                row = position.get('row', 'N/A')
                column = position.get('column', 'N/A')
                print(f"Position: (row {row}, column {column})")
                
                print(f"Title: {gadget.get('title', 'N/A')}")
                print(f"Module Key: {gadget.get('moduleKey', 'N/A')}")
                print(f"Color: {gadget.get('color', 'N/A')}")
                
                # Show properties if they exist
                properties = gadget.get('properties', {})
                if properties:
                    print("Properties:")
                    for key, value in properties.items():
                        print(f"  {key}: {value}")
                
                print("-" * 40)
            
            if not filtered_gadgets:
                if filter_type:
                    print(f"No gadgets found matching filter '{filter_type}'")
                else:
                    print("No gadgets found in dashboard")
            
            return True
            
        elif response.status_code == 404:
            print(f"✗ Dashboard {dashboard_id} not found")
            return False
        elif response.status_code == 403:
            print("✗ Access denied. Check your permissions for this dashboard")
            return False
        else:
            print(f"✗ Failed to fetch dashboard gadgets. Status: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"✗ Error connecting to Jira API: {e}")
        return False


def main():
    """Main entry point for jira-dashboard command."""
    args = docopt(__doc__, version=VERSION)
    
    dashboard_id = args['<dashboard_id>']
    filter_type = args['--filter']
    search_query = args['--search']
    show_raw = args['--raw']
    properties_gadget_id = args['--properties']
    config_gadget_id = args['--config']
    
    try:
        config = JiraConfigFile()
        
        # If --config is provided, show gadgetConfig for specific gadget
        if config_gadget_id:
            if not dashboard_id:
                print("✗ Error: Dashboard ID is required when using --config")
                return 1
            
            if search_query:
                print("Warning: --search option ignored when --config is provided")
                print()
            if filter_type:
                print("Warning: --filter option ignored when --config is provided")
                print()
            if properties_gadget_id:
                print("Warning: --properties option ignored when --config is provided")
                print()
            
            success = get_gadget_config(config, dashboard_id, config_gadget_id, show_raw)
        # If --properties is provided, show properties for specific gadget
        elif properties_gadget_id:
            if not dashboard_id:
                print("✗ Error: Dashboard ID is required when using --properties")
                return 1
            
            if search_query:
                print("Warning: --search option ignored when --properties is provided")
                print()
            if filter_type:
                print("Warning: --filter option ignored when --properties is provided")
                print()
            
            success = get_gadget_properties(config, dashboard_id, properties_gadget_id, show_raw)
        # If no dashboard ID provided, list dashboards
        elif not dashboard_id:
            success = list_dashboards(config, search_query)
        else:
            # If search query provided with dashboard ID, warn user
            if search_query:
                print("Warning: --search option ignored when dashboard ID is provided")
                print()
            
            success = list_dashboard_items(config, dashboard_id, filter_type, show_raw)
        
        return 0 if success else 1
        
    except KeyError as e:
        print(f"✗ Configuration error: {e}")
        print("\nCreate ~/.jira/config.ini with:")
        print("[Jira]")
        print("domain = your-domain")
        print("email = your-email@example.com")
        print("api_token = your-api-token")
        return 1
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        return 1


if __name__ == '__main__':
    exit(main())