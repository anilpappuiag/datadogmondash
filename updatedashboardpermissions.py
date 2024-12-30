from datadog_api_client import ApiClient, Configuration
from datadog_api_client.v2.api.audit_api import AuditApi
from datadog_api_client.v2.api.restriction_policies_api import RestrictionPoliciesApi
from datadog_api_client.v1.api.dashboards_api import DashboardsApi
from datadog_api_client.v2.api.teams_api import TeamsApi
from datadog_api_client.v2.models import *

# Datadog site configuration
DATADOG_SITE = "datadoghq.eu"

# Replace with your Datadog API and application keys
DATADOG_API_KEY = "////"
DATADOG_APP_KEY = "///"


def get_dashboards_created_last_minute():
    """
    Fetch the IDs of dashboards created in the last minute from Datadog's audit logs.

    Returns:
        list: A list of dashboard IDs created in the last minute, or an empty list if none were found.
    """
    dashboard_ids = []
    next_page_token = None

    configuration = Configuration()
    configuration.server_variables["site"] = DATADOG_SITE
    configuration.api_key["apiKeyAuth"] = DATADOG_API_KEY
    configuration.api_key["appKeyAuth"] = DATADOG_APP_KEY

    with ApiClient(configuration) as api_client:
        api_instance = AuditApi(api_client)

        while True:
            body = AuditLogsSearchEventsRequest(
                filter=AuditLogsQueryFilter(
                    _from="now-1m",
                    query="@evt.name:Dashboard AND @action:created",
                    to="now"
                ),
                options=AuditLogsQueryOptions(
                    time_offset=0,
                    timezone="GMT"
                ),
                page=AuditLogsQueryPageOptions(
                    limit=10,
                    cursor=next_page_token
                ),
                sort=AuditLogsSort.TIMESTAMP_ASCENDING
            )

            response = api_instance.search_audit_logs(body=body)

            dashboard_ids.extend([
                event.attributes.attributes['asset']['id']
                for event in response.data
            ])

            next_page_token = (
                response.meta.page.after 
                if response.meta and response.meta.page and response.meta.page.after 
                else None
            )

            if not next_page_token:
                break

    return dashboard_ids


def get_dashboard_creator_user_id(dashboard_id):
    """
    Retrieve the user who created the dashboard from audit logs.

    Args:
        dashboard_id (str): The ID of the dashboard.

    Returns:
        str: The user ID associated with the dashboard's creation.
    """
    configuration = Configuration()
    configuration.server_variables["site"] = DATADOG_SITE
    configuration.api_key["apiKeyAuth"] = DATADOG_API_KEY
    configuration.api_key["appKeyAuth"] = DATADOG_APP_KEY

    with ApiClient(configuration) as api_client:
        api_instance = AuditApi(api_client)
        body = AuditLogsSearchEventsRequest(
            filter=AuditLogsQueryFilter(
                _from="now-1m",
                query=f"@evt.name:Dashboard AND @action:created AND @asset.id:{dashboard_id}",
                to="now"
            )
        )
        response = api_instance.search_audit_logs(body=body)
        for event in response.data:
            return event.attributes.attributes.get('user', {}).get('id')


def get_team_uuid_by_user_id(user_id):
    """
    Fetch the team UUID associated with a user via their memberships.

    Args:
        user_id (str): The UUID of the user.

    Returns:
        str: The team's UUID, or None if not found.
    """
    configuration = Configuration()
    configuration.server_variables["site"] = DATADOG_SITE
    configuration.api_key["apiKeyAuth"] = DATADOG_API_KEY
    configuration.api_key["appKeyAuth"] = DATADOG_APP_KEY

    with ApiClient(configuration) as api_client:
        api_instance = TeamsApi(api_client)
        try:
            response = api_instance.get_user_memberships(user_uuid=user_id)
            for team in response.data:
                return team.id  # Return the first associated team UUID
        except Exception as e:
            print(f"⚠️ Error fetching team memberships for user {user_id}: {e}")
            return None


def set_dashboard_permissions(team_uuid, dashboard_id):
    """
    Set restriction policies for a dashboard, assigning permissions to a team.

    Args:
        team_uuid (str): The UUID of the team.
        dashboard_id (str): The ID of the dashboard.
    """
    body = RestrictionPolicyUpdateRequest(
        data=RestrictionPolicy(
            id=f"dashboard:{dashboard_id}",
            type=RestrictionPolicyType.RESTRICTION_POLICY,
            attributes=RestrictionPolicyAttributes(
                bindings=[
                    RestrictionPolicyBinding(
                        relation="editor",
                        principals=[
                            f"team:{team_uuid}",  # Assign editor role to the team
                            "role:e5091040-1d03-11ef-9dbc-da7ad0900005"
                        ],
                    ),
                    RestrictionPolicyBinding(
                        relation="viewer",
                        principals=[
                            "org:e4f8bb8c-1d03-11ef-9b95-da7ad0900005"
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
            resource_id=f"dashboard:{dashboard_id}", 
            body=body
        )


def lambda_handler():
    """
    Lambda handler function to fetch newly created dashboards and assign permissions.
    """
    try:
        dashboard_ids = get_dashboards_created_last_minute()
        if dashboard_ids:
            for dashboard_id in dashboard_ids:
                try:
                    user_id = get_dashboard_creator_user_id(dashboard_id)
                    if not user_id:
                        print(f"⚠️ No user found for dashboard {dashboard_id}. Skipping.")
                        continue

                    team_uuid = get_team_uuid_by_user_id(user_id)
                    if not team_uuid:
                        print(f"⚠️ No team UUID found for user {user_id}. Skipping dashboard {dashboard_id}.")
                        continue

                    set_dashboard_permissions(team_uuid, dashboard_id)
                    print(f"✅ Permissions set for dashboard ID: {dashboard_id}")

                except Exception as dashboard_error:
                    print(f"❌ Failed to process dashboard {dashboard_id}: {dashboard_error}")
        else:
            print("ℹ️ No dashboards were created in the last minute.")
    except Exception as e:
        print(f"🚨 An error occurred: {e}")


# Invoke the Lambda handler
lambda_handler()
