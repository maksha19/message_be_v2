import boto3
import json
import os
from datetime import datetime, timedelta
from botocore.exceptions import ClientError
from ec2Client import terminate_aws_ec2_instance

dynamodb = boto3.client('dynamodb')

def format_json_response(message, status_code=200):
    """Format standardized JSON response"""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization'
        },
        'body': json.dumps(message)
    }

def validate_environment_variables():
    """Validate required environment variables"""
    required_vars = ['USER_TABLE', 'USER_SUBSCRIPTION_TABLE', 'ENGINE_INSTANCE_TABLE', 'EVENT_TABLE']
    missing_vars = []
    
    for var in required_vars:
        if not os.environ.get(var):
            missing_vars.append(var)
    
    if missing_vars:
        raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")
    
    return {
        'USER_TABLE': os.environ.get('USER_TABLE'),
        'USER_SUBSCRIPTION_TABLE': os.environ.get('USER_SUBSCRIPTION_TABLE'),
        'ENGINE_INSTANCE_TABLE': os.environ.get('ENGINE_INSTANCE_TABLE'),
        'EVENT_TABLE': os.environ.get('EVENT_TABLE')
    }

def get_user_info(user_id, user_table):
    """Get user information from database"""
    try:
        response = dynamodb.get_item(
            TableName=user_table,
            Key={'userId': {'S': user_id}}
        )
        
        user_item = response.get('Item')
        if not user_item:
            raise ValueError('User not found')
        
        if not user_item.get('isActive', {}).get('BOOL', False):
            raise ValueError('User account is inactive')
        
        return {
            'name': user_item.get('name', {}).get('S', 'Unknown User'),
            'email': user_id,
            'phone': user_item.get('phone', {}).get('S', ''),
            'createdTime': int(user_item.get('createdTime', {}).get('N', 0)),
            'isActive': user_item.get('isActive', {}).get('BOOL', False)
        }
    except ClientError as e:
        print(f"Error getting user info: {e}")
        raise ValueError('Failed to retrieve user information')

def get_user_subscription(user_id, subscription_table):
    """Get user subscription information"""
    try:
        response = dynamodb.get_item(
            TableName=subscription_table,
            Key={'userId': {'S': user_id}}
        )
        
        subscription_item = response.get('Item')
        if not subscription_item:
            # Return default subscription if not found
            return {
                'messageCountUsed': 0,
                'messageCountLeft': 100,
                'engineHourUsed': 0,
                'engineHourLeft': 10
            }
        
        return {
            'messageCountUsed': int(subscription_item.get('messageCountUsed', {}).get('N', 0)),
            'messageCountLeft': int(subscription_item.get('messageCountLeft', {}).get('N', 100)),
            'engineHourUsed': int(subscription_item.get('engineHourUsed', {}).get('N', 0)),
            'engineHourLeft': int(subscription_item.get('engineHourLeft', {}).get('N', 10))
        }
    except ClientError as e:
        print(f"Error getting subscription info: {e}")
        raise ValueError('Failed to retrieve subscription information')

def get_active_instance(user_id, engine_table):
    """Get user's active WhatsApp instance"""
    try:
        response = dynamodb.query(
            TableName=engine_table,
            KeyConditionExpression='userId = :userId',
            FilterExpression='isActive = :isActive',
            ExpressionAttributeValues={
                ':userId': {'S': user_id},
                ':isActive': {'BOOL': True}
            }
        )
        
        instances = response.get('Items', [])
        if not instances:
            return None
        
        # Return the most recent active instance
        active_instance = instances[0]
        return {
            'instanceId': active_instance.get('instanceId', {}).get('S', ''),
            'createdTime': int(active_instance.get('createdTime', {}).get('N', 0)),
            'whatsappLinkTime': int(active_instance.get('whatsappLinkTime', {}).get('N', 0)) if active_instance.get('whatsappLinkTime') else None,
            'isActive': active_instance.get('isActive', {}).get('BOOL', False)
        }
    except ClientError as e:
        print(f"Error getting active instance: {e}")
        return None

def get_recent_events(user_id, event_table, limit=10):
    """Get user's recent broadcast events"""
    try:
        # Get events from the last 30 days
        thirty_days_ago = int((datetime.now() - timedelta(days=30)).timestamp())
        
        response = dynamodb.query(
            TableName=event_table,
            KeyConditionExpression='userId = :userId',
            FilterExpression='createdTime >= :thirtyDaysAgo',
            ExpressionAttributeValues={
                ':userId': {'S': user_id},
                ':thirtyDaysAgo': {'N': str(thirty_days_ago)}
            },
            ScanIndexForward=False,  # Sort by sort key in descending order
            Limit=limit
        )
        
        events = []
        for item in response.get('Items', []):
            events.append({
                'eventId': item.get('eventId', {}).get('S', ''),
                'title': item.get('title', {}).get('S', 'Untitled Event'),
                'description': item.get('description', {}).get('S', ''),
                'messageText': item.get('messageText', {}).get('S', ''),
                'recipientCount': int(item.get('recipientCount', {}).get('N', 0)),
                'successCount': int(item.get('successCount', {}).get('N', 0)),
                'failureCount': int(item.get('failureCount', {}).get('N', 0)),
                'status': item.get('status', {}).get('S', 'unknown'),
                'createdTime': int(item.get('createdTime', {}).get('N', 0)),
                'completedTime': int(item.get('completedTime', {}).get('N', 0)) if item.get('completedTime') else None
            })
        
        return events
    except ClientError as e:
        print(f"Error getting recent events: {e}")
        return []

def calculate_usage_stats(subscription_info, recent_events):
    """Calculate usage statistics"""
    # Calculate message usage percentage
    total_messages = subscription_info['messageCountUsed'] + subscription_info['messageCountLeft']
    message_usage_percentage = (subscription_info['messageCountUsed'] / total_messages * 100) if total_messages > 0 else 0
    
    # Calculate engine hour usage percentage
    total_hours = subscription_info['engineHourUsed'] + subscription_info['engineHourLeft']
    hour_usage_percentage = (subscription_info['engineHourUsed'] / total_hours * 100) if total_hours > 0 else 0
    
    # Calculate recent activity stats
    recent_messages_sent = sum(event.get('successCount', 0) for event in recent_events)
    recent_campaigns = len(recent_events)
    
    # Calculate success rate
    total_sent = sum(event.get('successCount', 0) + event.get('failureCount', 0) for event in recent_events)
    success_rate = (sum(event.get('successCount', 0) for event in recent_events) / total_sent * 100) if total_sent > 0 else 0
    
    return {
        'messageUsagePercentage': round(message_usage_percentage, 1),
        'hourUsagePercentage': round(hour_usage_percentage, 1),
        'recentMessagesSent': recent_messages_sent,
        'recentCampaigns': recent_campaigns,
        'successRate': round(success_rate, 1)
    }

def get_whatsapp_status(active_instance,user_id, engine_table):
    """Determine WhatsApp connection status"""
    status ={
        'status': 'disconnected',
        'statusText': 'Not Connected',
        'lastConnected': None,
        'instanceId': None
    }
    if not active_instance:
        return status
    
    instance_id = active_instance.get('instanceId')
    terminate_aws_ec2_instance(instance_id)
    # Mark instance as inactive in database
    update_params = {
            'TableName': engine_table,
            'Key': {
                'userId': {'S': user_id},
                'instanceId': {'S': instance_id}
            },
            'UpdateExpression': 'SET isActive = :isActive, terminatedTime = :terminatedTime',
            'ExpressionAttributeValues': {
                ':isActive': {'BOOL': False},
                ':terminatedTime': {'N': str(int(datetime.now().timestamp()))}
            }
        }
    dynamodb.update_item(**update_params)
    return status

def lambda_handler(event, context):
    """Main Lambda handler for dashboard summary"""
    try:
        print("Dashboard summary request:", json.dumps(event, indent=2))
        
        # Validate environment variables
        tables = validate_environment_variables()
        
        # Extract user ID from event (assuming it comes from authenticated context)
        user_id = None
        
        # Try to get user ID from different sources
        if 'requestContext' in event and 'authorizer' in event['requestContext']:
            # From API Gateway authorizer
            user_id = event['requestContext']['authorizer'].get('userId')
        elif 'pathParameters' in event and event['pathParameters']:
            # From path parameters
            user_id = event['pathParameters'].get('userId')
        elif 'queryStringParameters' in event and event['queryStringParameters']:
            # From query parameters
            user_id = event['queryStringParameters'].get('userId')
        
        # For development/testing, allow user ID from body
        if not user_id and 'body' in event:
            body = event['body']
            if isinstance(body, str):
                try:
                    body = json.loads(body)
                    user_id = body.get('userId')
                except json.JSONDecodeError:
                    pass
        
        if not user_id:
            return format_json_response({'message': 'User ID is required'}, 401)
        
        # Get user information
        user_info = get_user_info(user_id, tables['USER_TABLE'])
        
        # Get subscription information
        subscription_info = get_user_subscription(user_id, tables['USER_SUBSCRIPTION_TABLE'])
        
        # Get active WhatsApp instance
        active_instance = get_active_instance(user_id, tables['ENGINE_INSTANCE_TABLE'])
        
        # Get recent events/campaigns
        recent_events = get_recent_events(user_id, tables['EVENT_TABLE'])
        
        # Calculate usage statistics
        usage_stats = calculate_usage_stats(subscription_info, recent_events)
        
        # Get WhatsApp status
        whatsapp_status = get_whatsapp_status(active_instance,user_id, tables['ENGINE_INSTANCE_TABLE'])
        
        # Prepare dashboard summary response
        dashboard_summary = {
            'user': {
                'name': user_info['name'],
                'email': user_info['email'],
                'memberSince': user_info['createdTime']
            },
            'subscription': {
                'messagesSent': subscription_info['messageCountUsed'],
                'messagesLeft': subscription_info['messageCountLeft'],
                'hoursUsed': subscription_info['engineHourUsed'],
                'hoursLeft': subscription_info['engineHourLeft']
            },
            'usage': usage_stats,
            'whatsapp': whatsapp_status,
            'recentActivity': recent_events[:5],  # Return only 5 most recent
            'summary': {
                'totalCampaigns': len(recent_events),
                'totalMessagesSent': usage_stats['recentMessagesSent'],
                'averageSuccessRate': usage_stats['successRate']
            }
        }
        
        return format_json_response({
            'success': True,
            'data': dashboard_summary
        })
        
    except ValueError as ve:
        print(f"Validation error: {ve}")
        return format_json_response({'message': str(ve)}, 400)
    except Exception as e:
        print(f"Unexpected error: {e}")
        return format_json_response({'message': 'Internal server error'}, 500)