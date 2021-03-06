#!/usr/bin/env python2

# Import AWS Scout2 tools
from AWSScout2.utils import *
from AWSScout2.findings import *

# Import other third-party packages
import json
import urllib


########################################
##### IAM functions
########################################

def analyze_iam_config(iam_info, force_write):
    sys.stdout.write('Analyzing IAM data...\n')
    analyze_config(iam_finding_dictionary, iam_info, 'IAM', force_write)

def get_groups_info(iam_connection, iam_info):
    groups = handle_truncated_responses(iam_connection.get_all_groups, None, ['list_groups_response', 'list_groups_result'], 'groups')
    count, total = init_status(groups)
    for group in groups:
        group['users'] = get_group_users(iam_connection, group.group_name);
        group['policies'] = get_policies(iam_connection, iam_info, 'group', group.group_name)
        iam_info['groups'][group.group_name] = group
        count = update_status(count, total)
    close_status(count, total)

def get_group_users(iam, group_name):
    users = []
    fetched_users = iam.get_group(group_name).get_group_response.get_group_result.users
    for user in fetched_users:
        users.append(user.user_name)
    return users

def get_iam_info(key_id, secret, session_token):
    iam_info = {}
    manage_dictionary(iam_info, 'groups', {})
    manage_dictionary(iam_info, 'permissions', {})
    manage_dictionary(iam_info, 'roles', {})
    manage_dictionary(iam_info, 'users', {})
    iam_connection = boto.connect_iam(aws_access_key_id = key_id, aws_secret_access_key = secret, security_token = session_token)
    print 'Fetching IAM users data...'
    get_users_info(iam_connection, iam_info)
    print 'Fetching IAM groups data...'
    get_groups_info(iam_connection, iam_info)
    print 'Fetching IAM roles data...'
    get_roles_info(iam_connection, iam_info)
    return iam_info

def get_permissions(policy_document, permissions, keyword, name, policy_name):
    manage_dictionary(permissions, 'Action', {})
    manage_dictionary(permissions, 'NotAction', {})
    document = json.loads(urllib.unquote(policy_document).decode('utf-8'))
    for statement in document['Statement']:
        effect = str(statement['Effect'])
        action_string = 'Action' if 'Action' in statement else 'NotAction'
        parse_actions(permissions[action_string], statement[action_string], statement['Resource'], effect, keyword, name, policy_name)

def parse_actions(permissions, actions, resources, effect, keyword, name, policy_name):
    if type(actions) == list:
        for action in actions:
            parse_action(permissions, action, resources, effect, keyword, name, policy_name)
    else:
        parse_action(permissions, actions, resources, effect, keyword, name, policy_name)

def parse_action(permissions, action, resources, effect, keyword, name, policy_name):
    manage_dictionary(permissions, action, {})
    parse_resources(permissions[action], resources, effect, keyword, name, policy_name)

def parse_resources(permission, resources, effect, keyword, name, policy_name):
    if type(resources) == list:
        for resource in resources:
            parse_resource(permission, resource, effect, keyword, name, policy_name)
    else:
        parse_resource(permission, resources, effect, keyword, name, policy_name)

def parse_resource(permission, resource, effect, keyword, name, policy_name):
    manage_dictionary(permission, keyword, {})
    # h4ck : data redundancy because I can't call ../@key in Handlebars
    permission[keyword]['type'] = keyword
    manage_dictionary(permission[keyword], name, {})
    manage_dictionary(permission[keyword][name], effect, [])
    permission[keyword][name][effect].append(resource)

def get_policies(iam_connection, iam_info, keyword, name):
    fetched_policies = []
    if keyword == 'role':
        m1 = getattr(iam_connection, 'list_role_policies', None)
    else:
        m1 = getattr(iam_connection, 'get_all_' + keyword + '_policies', None)
    if m1:
        policy_names = m1(name)
    else:
        print 'Unknown error' # fetched_policies, permissions
    policy_names = policy_names['list_' + keyword + '_policies_response']['list_' + keyword + '_policies_result']['policy_names']
    get_policy_method = getattr(iam_connection, 'get_' + keyword + '_policy')
    for policy_name in policy_names:
        r = get_policy_method(name, policy_name)
        r = r['get_'+keyword+'_policy_response']['get_'+keyword+'_policy_result']
        pdetails = {}
        pdetails['policy_name'] = policy_name
        pdetails['policy_document'] = r.policy_document
        fetched_policies.append(pdetails)
        get_permissions(pdetails['policy_document'], iam_info['permissions'], keyword + 's', name, pdetails['policy_name'])
    return fetched_policies


def get_roles_info(iam_connection, iam_info):
    roles = handle_truncated_responses(iam_connection.list_roles, None, ['list_roles_response', 'list_roles_result'], 'roles')
    count, total = init_status(roles)
    for role in roles:
        role['policies'] = get_policies(iam_connection, iam_info, 'role', role.role_name)
        iam_info['roles'][role.role_name] = role
        count = update_status(count, total)
        profiles = handle_truncated_responses(iam_connection.list_instance_profiles_for_role, role.role_name, ['list_instance_profiles_for_role_response', 'list_instance_profiles_for_role_result'], 'instance_profiles')
        manage_dictionary(role, 'instance_profiles', {})
        for profile in profiles:
            manage_dictionary(role['instance_profiles'], profile['arn'], {})
            role['instance_profiles'][profile['arn']]['id'] = profile['instance_profile_id']
            role['instance_profiles'][profile['arn']]['name'] = profile['instance_profile_name']
    close_status(count, total)

def get_users_info(iam_connection, iam_info):
    users = handle_truncated_responses(iam_connection.get_all_users, None, ['list_users_response', 'list_users_result'], 'users')
    count, total = init_status(users)
    for user in users:
        user['policies'] = get_policies(iam_connection, iam_info, 'user', user.user_name)
        groups = iam_connection.get_groups_for_user(user['user_name'])
        user['groups'] = groups.list_groups_for_user_response.list_groups_for_user_result.groups
        try:
            logins = iam_connection.get_login_profiles(user['user_name'])
            user['logins'] = logins.get_login_profile_response.get_login_profile_result.login_profile
        except Exception, e:
            pass
        access_keys = iam_connection.get_all_access_keys(user['user_name'])
        user['access_keys'] = access_keys.list_access_keys_response.list_access_keys_result.access_key_metadata
        mfa_devices = iam_connection.get_all_mfa_devices(user['user_name'])
        user['mfa_devices'] = mfa_devices.list_mfa_devices_response.list_mfa_devices_result.mfa_devices
        user['user_name']
        iam_info['users'][user['user_name']] = user
        count = update_status(count, total)
    close_status(count, total)

def handle_truncated_responses(callback, callback_args, result_path, items_name):
    marker_value = None
    items = []
    while True:
        if callback_args:
            result = callback(callback_args, marker = marker_value)
        else:
            result = callback(marker = marker_value)
        for key in result_path:
            result = result[key]
        marker_value = result['marker'] if result['is_truncated'] != 'false' else None
        items = items + result[items_name]
        if marker_value is None:
            break
    return items
