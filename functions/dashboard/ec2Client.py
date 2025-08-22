import boto3
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# AWS Configuration
aws_region = 'ap-southeast-1'
aws_access_key_id = "abc"
aws_secret_access_key = "dfd"

ec2 = boto3.client('ec2', region_name=aws_region, aws_access_key_id=aws_access_key_id, aws_secret_access_key=aws_secret_access_key)

def terminate_aws_ec2_instance(instance_id):
    try:
        if not instance_id:
            raise ValueError("Instance ID is required to terminate an EC2 instance.")
        
        response = ec2.terminate_instances(InstanceIds=[instance_id])
        if 'TerminatingInstances' not in response or not response['TerminatingInstances']:
            raise RuntimeError("Failed to terminate EC2 instance. No termination information returned.")
        
        logger.info('EC2 Instance terminated: %s', response['TerminatingInstances'])
        return response['TerminatingInstances']
    except boto3.exceptions.Boto3Error as boto_err:
        logger.error('AWS SDK error while terminating EC2 instance: %s', boto_err)
    except Exception as err:
        logger.error('Error terminating EC2 instance: %s', err)
    return None

def call_describe_instances(params):
    try:
        if not params:
            raise ValueError("Parameters are required to describe EC2 instances.")
        
        response = ec2.describe_instances(**params)
        logger.info('Describe Instances response: %s', response)
        return response
    except boto3.exceptions.Boto3Error as boto_err:
        logger.error('AWS SDK error while describing EC2 instances: %s', boto_err)
    except Exception as err:
        logger.error('Error describing EC2 instances: %s', err)
    return None