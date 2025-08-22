import boto3
import hashlib
import hmac
import json
import os
from datetime import datetime

dynamodb = boto3.client('dynamodb')

SWEET = 'MakSHA256'

def hash_password(password: str) -> str:
    return hmac.new(SWEET.encode(), password.encode(), hashlib.sha512).hexdigest()

def get_db_params(table_name: str, user_id: str):
    return {
        'TableName': table_name,
        'Key': {
            'userId': {'S': user_id}
        }
    }

def format_json_response(message, status_code=200):
    return {
        'statusCode': status_code,
        'body': json.dumps(message)
    }

def lambda_handler(event, context):
    try:
        print("Received event:", json.dumps(event, indent=2))
        # Validate environment variables
        USER_TABLE = os.environ.get('USER_TABLE')
        USER_SUBSCRIPTION = os.environ.get('USER_SUBSCRIPTION_TABLE')
        USER_LOGIN = os.environ.get('USER_LOGIN_TABLE')
        print("USER_TABLE",USER_TABLE)
        print("USER_SUBSCRIPTION",USER_SUBSCRIPTION)
        print("USER_LOGIN_TABLE",USER_LOGIN)

        if not USER_TABLE or not USER_SUBSCRIPTION or not USER_LOGIN:
            raise ValueError("Missing required environment variables")

        # Validate event body
        if 'body' not in event:
            raise ValueError("Request body is missing")

        body = json.loads(event['body'])
        user_id = body.get('userId')
        password = body.get('password')
        action = body.get('action')
        name = body.get('name')
        phone = body.get('phone')

        if not action:
            raise ValueError("Action is required")

        if action.upper() == "SINGUP":
            if not user_id or not password or not name or not phone:
                return format_json_response({'message': 'userId, password, name, and phone are required'}, 400)

            try:
                db_params_user = get_db_params(USER_TABLE, user_id)
                user_info = dynamodb.get_item(**db_params_user).get('Item')

                if user_info:
                    return format_json_response({'message': 'User already exists'}, 409)

                hashed_password = hash_password(password)
                now_date = int(datetime.now().timestamp())

                dynamodb.put_item(
                    TableName=USER_TABLE,
                    Item={
                        'userId': {'S': user_id},
                        'name': {'S': name},
                        'password': {'S': hashed_password},
                        'phone': {'S': phone},
                        'isActive': {'BOOL': True},
                        'createdTime': {'N': str(now_date)},
                        'modifiedTime': {'N': str(now_date)},
                    }
                )

                dynamodb.put_item(
                    TableName=USER_SUBSCRIPTION,
                    Item={
                        'userId': {'S': user_id},
                        'messageCountUsed': {'N': '0'},
                        'messageCountLeft': {'N': '0'},
                        'engineHourUsed': {'N': '0'},
                        'engineHourLeft': {'N': '0'},
                        'modifiedTime': {'N': str(now_date)},
                    }
                )

                dynamodb.put_item(
                    TableName=USER_LOGIN,
                    Item={
                        'userId': {'S': user_id},
                        'loginInTime': {'S': str(now_date)},
                        'modifiedTime': {'N': str(now_date)},
                    }
                )

                return format_json_response({
                    'message': 'User account created successfully',
                    'userId': user_id,
                    'messageCountUsed': 0,
                    'messageCountLeft': 0,
                    'engineHourUsed': 0,
                    'engineHourLeft': 0
                })

            except Exception as err:
                print(f"Signup error: {err}")
                return format_json_response({'message': 'Error during signup', 'details': str(err)}, 500)

        elif action.upper() == 'LOGIN':
            if not user_id or not password:
                return format_json_response({'message': 'userId and password are required'}, 400)

            try:
                hashed_password = hash_password(password)
                db_params = get_db_params(USER_TABLE, user_id)
                user_info = dynamodb.get_item(**db_params).get('Item')

                if not user_info or not user_info.get('isActive', {}).get('BOOL'):
                    return format_json_response({'message': 'UserId or Password might be incorrect'}, 403)

                if user_info['password']['S'] == hashed_password:
                    db_params = get_db_params(USER_SUBSCRIPTION, user_id)
                    user_subscription_info = dynamodb.get_item(**db_params).get('Item')

                    if not user_subscription_info:
                        return format_json_response({'message': 'User subscription not found'}, 404)

                    now_date = int(datetime.now().timestamp())
                    dynamodb.put_item(
                        TableName=USER_LOGIN,
                        Item={
                            'userId': {'S': user_id},
                            'loginInTime': {'S': str(now_date)},
                            'modifiedTime': {'N': str(now_date)},
                        }
                    )

                    responses = {
                        'name': user_info['name']['S'],
                        'messageCountUsed': int(user_subscription_info['messageCountUsed']['N']),
                        'messageCountLeft': int(user_subscription_info['messageCountLeft']['N']),
                        'engineHourUsed': int(user_subscription_info['engineHourUsed']['N']),
                        'engineHourLeft': int(user_subscription_info['engineHourLeft']['N']),
                        'message': 'Successfully logged in'
                    }
                    return format_json_response(responses)

                else:
                    return format_json_response({'message': 'UserId or Password might be incorrect'}, 403)

            except Exception as error:
                print(f"Login error: {error}")
                return format_json_response({'message': 'Error during login', 'details': str(error)}, 500)

        elif action.upper() == 'LOGOUT':
            if not user_id:
                return format_json_response({'message': 'userId is required'}, 400)
            
            return format_json_response({'message': 'Successfully logged out'})
            try:
                db_params = get_db_params(USER_LOGIN, user_id)
                user_login_info = dynamodb.get_item(**db_params).get('Item')

                if not user_login_info:
                    return format_json_response({'message': 'User login information not found'}, 404)

                now_date = int(datetime.now().timestamp())
                dynamodb.update_item(
                    TableName=USER_LOGIN,
                    Key={'userId': {'S': user_id}},
                    UpdateExpression='SET logoutTime = :logoutTime',
                    ExpressionAttributeValues={':logoutTime': {'N': str(now_date)}}
                )

                return format_json_response({'message': 'Successfully logged out'})

            except Exception as error:
                print(f"Logout error: {error}")
                return format_json_response({'message': 'Error during logout', 'details': str(error)}, 500)

        else:
            return format_json_response({'message': 'Unsupported action'}, 400)

    except ValueError as ve:
        print(f"Validation error: {ve}")
        return format_json_response({'message': str(ve)}, 400)

    except Exception as e:
        print(f"Unexpected error: {e}")
        return format_json_response({'message': 'Internal server error', 'details': str(e)}, 500)
