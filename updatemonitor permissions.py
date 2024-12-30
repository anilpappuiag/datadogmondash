from datadog_api_client import ApiClient, Configuration
from datadog_api_client.v2.api.audit_api import AuditApi
from datadog_api_client.v2.api.restriction_policies_api import RestrictionPoliciesApi
from datadog_api_client.v1.api.monitors_api import MonitorsApi
from datadog_api_client.v2.api.teams_api import TeamsApi
from datadog_api_client.v2.models import *

# Datadog site configuration - Adjust based on your Datadog region (e.g., datadoghq.eu or datadoghq.com)
DATADOG_SITE = "datadoghq.eu"

# Replace the following with your Datadog API and application keys
DATADOG_API_KEY = "////"
DATADOG_APP_KEY = "///"


def get_monitors_created_last_minute():
    """
    Fetch the IDs of monitors created in the last minute from Datadog's audit logs.

    Returns:
        list: A list of monitor IDs created in the last minute, or an empty list if none were found.
    """
    body = AuditLogsSearchEventsRequest(
        filter=AuditLogsQueryFilter(
            _from="now-1m",  # Time range: Last minute
            query="@evt.name:Monitor AND @action:created",  # Query to find created monitors
            to="now",  # Current time
        ),
        options=AuditLogsQueryOptions(
            time_offset=0,
            timezone="GMT",  # Ensure results are in GMT
        ),
        page=AuditLogsQueryPageOptions(
            limit=10,  # Limit the number of results to 10
        ),
        sort=AuditLogsSort.TIMESTAMP_ASCENDING,  # Sort results by timestamp in ascending order
    )

    configuration = Configuration()
    configuration.server_variables["site"] = DATADOG_SITE
    configuration.api_key["apiKeyAuth"] = DATADOG_API_KEY
    configuration.api_key["appKeyAuth"] = DATADOG_APP_KEY

    with ApiClient(configuration) as api_client:
        api_instance = AuditApi(api_client)
        response = api_instance.search_audit_logs(body=body)
        monitor_ids = [
            event.attributes.attributes['asset']['id']
            for event in response.data
        ]
    return monitor_ids


def get_monitor_team(monitor_id):
    """
    Retrieve the team associated with a monitor based on its tags.

    Args:
        monitor_id (int): The ID of the monitor.

    Returns:
        str: The team name associated with the monitor.
    """
    configuration = Configuration()
    configuration.server_variables["site"] = DATADOG_SITE
    configuration.api_key["apiKeyAuth"] = DATADOG_API_KEY
    configuration.api_key["appKeyAuth"] = DATADOG_APP_KEY

    with ApiClient(configuration) as api_client:
        api_instance = MonitorsApi(api_client)
        response = api_instance.get_monitor(int(monitor_id))
        tags = {item.split(":")[0]: item.split(":")[1] for item in response.tags}
        return tags['team']


def get_team_uuid_by_name(team_name):
    """
    Get the unique identifier (UUID) for a team by its name.

    Args:
        team_name (str): The name of the team.

    Returns:
        str: The team's UUID, or None if not found.
    """
    configuration = Configuration()
    configuration.server_variables["site"] = DATADOG_SITE
    configuration.api_key["apiKeyAuth"] = DATADOG_API_KEY
    configuration.api_key["appKeyAuth"] = DATADOG_APP_KEY

    with ApiClient(configuration) as api_client:
        teams_api = TeamsApi(api_client)
        try:
            response = teams_api.list_teams(filter_keyword=team_name)
            for team in response.data:
                return team.id
        except Exception as e:
            print(f"Error fetching team details: {e}")
            return None


def set_monitor_permissions(team_uuid, monitor_id):
    """
    Set restriction policies for a monitor, assigning permissions to a team.

    Args:
        team_uuid (str): The UUID of the team.
        monitor_id (int): The ID of the monitor.
    """
    body = RestrictionPolicyUpdateRequest(
        data=RestrictionPolicy(
            id="monitor:" + str(monitor_id),
            type=RestrictionPolicyType.RESTRICTION_POLICY,
            attributes=RestrictionPolicyAttributes(
                bindings=[
                    RestrictionPolicyBinding(
                        relation="editor",
                        principals=[
                            "team:" + str(team_uuid),  # Assign editor role to the team
                            "role:e5091040-1d03-11ef-9dbc-da7ad0900005"  # Additional role
                        ],
                    ),
                    RestrictionPolicyBinding(
                        relation="viewer",
                        principals=[
                            "org:e4f8bb8c-1d03-11ef-9b95-da7ad0900005",  # Viewer role for the organization
                        ],
                    ),
                ],
            ),
        ),
    )

    configuration = Configuration()
    configuration.server_variables["site"] = DATADOG_SITE
    configuration.api_key["apiKeyAuth"] = DATADOG_API_KEY
    configuration.api_key["appKeyAuth"] = DATADOG_APP_KEY

    with ApiClient(configuration) as api_client:
        api_instance = RestrictionPoliciesApi(api_client)
        api_instance.update_restriction_policy(
            resource_id="monitor:" + str(monitor_id), body=body
        )


def lambda_handler():
    """
    Lambda handler function to fetch newly created monitors and assign permissions.
    """
    try:
        monitor_ids = get_monitors_created_last_minute()
        if monitor_ids:
            for monitor_id in monitor_ids:
                team_uuid = get_team_uuid_by_name(get_monitor_team(monitor_id))
                if team_uuid:
                    set_monitor_permissions(team_uuid, monitor_id)
                    print(f"✅ Permissions set for monitor ID: {monitor_id}")
                else:
                    print(f"⚠️ Team UUID not found for monitor ID: {monitor_id}")
        else:
            print("ℹ️ No monitors were created in the last minute.")
    except Exception as e:
        print(f"🚨 An error occurred: {e}")


# Invoke the Lambda handler
lambda_handler()
