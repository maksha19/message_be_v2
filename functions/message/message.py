# message handler

import boto3
import requests
import os
import json
from datetime import datetime
from ec2Client import create_aws_ec2_instance, call_describe_instances, terminate_aws_ec2_instance

dynamodb = boto3.client('dynamodb')

def get_db_params(table, user_id):
    if not table or not user_id:
        raise ValueError('Table name and User ID cannot be empty')
    return {
        'TableName': table,
        'Key': {
            'userId': {'S': user_id}
        }
    }

def validate_user(user_id, user_table):
    try:
        if not user_id or user_id.strip() == '':
            raise ValueError('User ID cannot be empty')

        db_params = get_db_params(user_table, user_id)
        user_info = dynamodb.get_item(**db_params).get('Item')

        if not user_info or not user_info.get('isActive', {}).get('BOOL'):
            raise ValueError('User not found or inactive')
    except Exception as err:
        print(f"Error validating user: {err}")
        raise ValueError('Failed to validate user')

def validate_subscription(user_id, subscription_table):
    try:
        if not user_id or user_id.strip() == '':
            raise ValueError('User ID cannot be empty')

        db_params = get_db_params(subscription_table, user_id)
        subscription_info = dynamodb.get_item(**db_params).get('Item')

        if not subscription_info:
            raise ValueError('Subscription not found')

        if int(subscription_info.get('messageCountLeft', {}).get('N', 0)) <= 0:
            raise ValueError('Message count is zero')
    except Exception as err:
        print(f"Error validating subscription: {err}")
        raise ValueError('Failed to validate subscription')

def validate_public_url(public_url):
    if not public_url or public_url.strip() == '':
        raise ValueError('Public URL cannot be empty')

def update_whatsapp_link_time(engine_table, user_id, instance_id):
    try:
        if not instance_id:
            raise ValueError('Instance ID cannot be None')

        update_params = {
            'TableName': engine_table,
            'Key': {
                'userId': {'S': user_id},
                'instanceId': {'S': instance_id}
            },
            'UpdateExpression': 'SET whatsappLinkTime = :whatsappLinkTime',
            'ExpressionAttributeValues': {
                ':whatsappLinkTime': {'N': str(int(datetime.now().timestamp()))},
                ':isActive': {'BOOL': True}
            },
            'ConditionExpression': 'isActive = :isActive'
        }

        dynamodb.update_item(**update_params)
        print('Whatsapp link time updated successfully')
    except Exception as err:
        print(f"Error updating Whatsapp link time: {err}")
        raise ValueError('Failed to update Whatsapp link time')

def create_instance(user_id, engine_table):
    try:
        instance_id = None
        print(f"Creating instance for {user_id}")

        if os.environ.get('STAGE') == 'offline':
            instance_id = "offline_987654322"
        else:
            instance_id = create_aws_ec2_instance(user_id)

        if not instance_id:
            raise ValueError('Failed to create EC2 instance')

        print(f"Instance created with ID: {instance_id}")
        now_time = int(datetime.now().timestamp())
        db_params = {
            'TableName': engine_table,
            'Item': {
                'userId': {'S': user_id},
                'instanceId': {'S': instance_id},
                'createdTime': {'N': str(now_time)},
                'isActive': {'BOOL': True}
            }
        }

        dynamodb.put_item(**db_params)
        print('createInstance saved in DB')
        return instance_id
    except Exception as err:
        print(f"Error creating instance: {err}")
        raise ValueError('Failed to create instance')

def status_instance(user_id, instance_id):
    try:
        if os.environ.get('STAGE') == 'offline':
            return "localhost:3001"

        params = {
            'Filters': [
                {'Name': 'instance-state-name', 'Values': ['running']},
                {'Name': 'tag:UserId', 'Values': [user_id]}
            ],
            'InstanceIds': [instance_id]
        }
        data = call_describe_instances(**params)
        instance = data['Reservations'][0]['Instances'][0]
        public_url = instance.get('PublicIpAddress')
        if not public_url:
            raise ValueError('Public URL not found')
        return public_url
    except Exception as err:
        print(f"Error getting instance status: {err}")
        raise ValueError('Failed to get instance status')

def get_message_qr_code(public_url):
    try:
        validate_public_url(public_url)
        response = requests.get(f"http://{public_url}/qrCode")
        response.raise_for_status()
        return response.json().get('qrCode')
    except Exception as err:
        print(f"Error getting QR code: {err}")
        raise ValueError('Failed to get QR code')

def login_status(public_url, engine_table, user_id, instance_id):
    try:
        validate_public_url(public_url)
        response = requests.get(f"http://{public_url}/loginStatus")
        response.raise_for_status()

        if response.json().get('loginStatus'):
            update_whatsapp_link_time(engine_table, user_id, instance_id)
        return response.json().get('loginStatus')
    except Exception as err:
        print(f"Error getting login status: {err}")
        raise ValueError('Failed to get login status')

def log_out_and_terminate_instances(public_url, user_id, instance_id, event_table):
    try:
        validate_public_url(public_url)
        log_out_message = requests.get(f"http://{public_url}/logout")
        log_out_message.raise_for_status()
        terminate_instance(user_id, instance_id, event_table)
        return log_out_message.json().get('loginStatus')
    except Exception as err:
        print(f"Error logging out and terminating instances: {err}")
        raise ValueError('Failed to log out and terminate instances')

def send_message(public_url, message):
    try:
        if not message:
            raise ValueError('No message to send')

        validate_public_url(public_url)
        response = requests.post(f"http://{public_url}/sendMessage", json=message)
        response.raise_for_status()
        return response.json()
    except Exception as err:
        print(f"Error sending message: {err}")
        raise ValueError('Failed to send message')

def terminate_instance(user_id, instance_id, event_table):
    try:
        user_instance_id = instance_id

        if not user_instance_id:
            db_params = {
                'TableName': event_table,
                'Key': {
                    'userId': {'S': user_id}
                },
                'FilterExpression': 'isActive = :isActive',
                'ExpressionAttributeValues': {
                    ':isActive': {'BOOL': True}
                },
                'Limit': 1
            }
            user_instance_id = dynamodb.query(**db_params)['Items'][0]['eventId']['S']

        if os.environ.get('STAGE') != 'offline':
            terminate_aws_ec2_instance(user_instance_id)

        terminate_db_params = {
            'TableName': event_table,
            'Key': {
                'userId': {'S': user_id},
                'eventId': {'S': user_instance_id}
            },
            'UpdateExpression': 'SET terminatedTime = :terminatedTime',
            'ExpressionAttributeValues': {
                ':terminatedTime': {'N': str(int(datetime.now().timestamp()))}
            }
        }
        dynamodb.update_item(**terminate_db_params)
        return user_instance_id
    except Exception as err:
        print(f"Error terminating instance: {err}")
        raise ValueError('Failed to terminate instance')

def lambda_handler(event, context):
    try:
        print("Received event:", json.dumps(event, indent=2))
        
        body = {}
        if 'body' in event:
            body_temp = event['body']
            if isinstance(body_temp, str):
                try:
                    body = json.loads(body_temp)
                except json.JSONDecodeError:
                    pass
        user_id = body.get('userId')
        instance_id = body.get('instanceId')
        public_url = body.get('publicUrl')
        action = body.get('action')
        message = body.get('message')

        user_table = os.environ.get('USER_TABLE')
        event_table = os.environ.get('EVENT_TABLE')
        engine_table = os.environ.get('ENGINE_INSTANCE_TABLE')
        user_subscription = os.environ.get('USER_SUBSCRIPTION_TABLE')

        if not action:
            raise ValueError('Action cannot be empty')

        if action != "message":
            validate_user(user_id, user_table)
            validate_subscription(user_id, user_subscription)

        action_map = {
            "create": lambda: {
                'statusCode': 200,
                'body': json.dumps({'instanceId': create_instance(user_id, engine_table)})
            },
            "status": lambda: {
                'statusCode': 201,
                'body': json.dumps({'publicUrl': status_instance(user_id, instance_id)})
            },
            "qrcode": lambda: {
                'statusCode': 202,
                'body': json.dumps({'qrCode': get_message_qr_code(public_url)})
            },
            "loginStatus": lambda: {
                'statusCode': 203,
                'body': json.dumps({'loginStatus': login_status(public_url, engine_table, user_id, instance_id)})
            },
            "sendMessage": lambda: {
                'statusCode': 204,
                'body': json.dumps({'messageResponse': send_message(public_url, message)})
            },
            "logout": lambda: {
                'statusCode': 205,
                'body': json.dumps({'logOutandTerminateResponse': log_out_and_terminate_instances(public_url, user_id, instance_id, event_table)})
            },
            "terminate": lambda: {
                'statusCode': 206,
                'body': json.dumps({'instanceId': terminate_instance(user_id, instance_id, event_table)})
            },
        }

        return action_map.get(action, lambda: {
            'statusCode': 400,
            'body': json.dumps({'message': 'Invalid action'})
        })()
    except ValueError as err:
        print(f"Validation error: {err}")
        return {
            'statusCode': 400,
            'body': json.dumps({'message': str(err)})
        }
    except Exception as err:
        print(f"System error: {err}")
        return {
            'statusCode': 500,
            'body': json.dumps({'message': 'SYSTEM ERROR'})
        }
