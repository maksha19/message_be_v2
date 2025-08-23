import boto3
import base64
import logging
import time
from botocore.exceptions import ClientError, BotoCoreError


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# AWS Configuration
aws_region = 'ap-southeast-1'
aws_access_key_id = "abc"
aws_secret_access_key = "dfd"

# Initialize AWS clients with error handling
try:
    ec2 = boto3.client(
        'ec2', 
        region_name=aws_region, 
        aws_access_key_id=aws_access_key_id, 
        aws_secret_access_key=aws_secret_access_key
    )
    ssm = boto3.client(
        'ssm', 
        region_name=aws_region, 
        aws_access_key_id=aws_access_key_id, 
        aws_secret_access_key=aws_secret_access_key
    )
except Exception as e:
    logger.error(f"Failed to initialize AWS clients: {e}")
    raise

# EC2 instance parameter
def terminate_aws_ec2_instance(instance_id):
    """Terminate EC2 instance with proper error handling"""
    try:
        if not instance_id:
            raise ValueError("Instance ID is required to terminate an EC2 instance.")
        
        logger.info(f"Terminating EC2 instance: {instance_id}")
        
        # Check if instance exists and get its current state
        try:
            response = ec2.describe_instances(InstanceIds=[instance_id])
            if not response['Reservations']:
                logger.warning(f"Instance {instance_id} not found, may already be terminated")
                return {"message": "Instance not found or already terminated"}
                
            instance_state = response['Reservations'][0]['Instances'][0]['State']['Name']
            if instance_state in ['terminated', 'terminating']:
                logger.info(f"Instance {instance_id} is already {instance_state}")
                return {"message": f"Instance already {instance_state}"}
                
        except ClientError as e:
            if e.response['Error']['Code'] == 'InvalidInstanceID.NotFound':
                logger.warning(f"Instance {instance_id} not found")
                return {"message": "Instance not found"}
            raise
        
        # Terminate the instance
        response = ec2.terminate_instances(InstanceIds=[instance_id])
        
        if 'TerminatingInstances' not in response or not response['TerminatingInstances']:
            raise RuntimeError("Failed to terminate EC2 instance. No termination information returned.")
        
        termination_info = response['TerminatingInstances'][0]
        logger.info(f'EC2 Instance termination initiated: {termination_info}')
        
        return {
            "instanceId": instance_id,
            "currentState": termination_info.get('CurrentState', {}).get('Name'),
            "previousState": termination_info.get('PreviousState', {}).get('Name')
        }
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']
        logger.error(f'AWS ClientError terminating EC2 instance: {error_code} - {error_message}')
        
        if error_code == 'InvalidInstanceID.NotFound':
            return {"message": "Instance not found or already terminated"}
        elif error_code == 'UnauthorizedOperation':
            raise RuntimeError("Insufficient permissions to terminate EC2 instance")
        else:
            raise RuntimeError(f"AWS error terminating instance: {error_message}")
            
    except BotoCoreError as e:
        logger.error(f'BotoCoreError terminating EC2 instance: {e}')
        raise RuntimeError("Network or configuration error while terminating instance")
        
    except Exception as e:
        logger.error(f'Unexpected error terminating EC2 instance: {e}')
        raise RuntimeError(f"Failed to terminate EC2 instance: {str(e)}")