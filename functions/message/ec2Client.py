import boto3
import base64
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# AWS Configuration
aws_region = 'ap-southeast-1'
aws_access_key_id = "abc"
aws_secret_access_key = "dfd"

ec2 = boto3.client('ec2', region_name=aws_region, aws_access_key_id=aws_access_key_id, aws_secret_access_key=aws_secret_access_key)
ssm = boto3.client('ssm', region_name=aws_region, aws_access_key_id=aws_access_key_id, aws_secret_access_key=aws_secret_access_key)

params = {
    "ImageId": "ami-073e03612149d5c85",
    "InstanceType": "t3.micro",
    "MinCount": 1,
    "MaxCount": 1,
    "KeyName": "message",
    "SecurityGroupIds": ["sg-083ba73b7d582f339"],
    "SubnetId": "subnet-0febf74469aa28417",
    "InstanceInitiatedShutdownBehavior": "terminate",
    "IamInstanceProfile": {"Name": "message-ec2"},
    "BlockDeviceMappings": [
        {
            "DeviceName": "/dev/xvda",
            "Ebs": {
                "VolumeSize": 8,
                "VolumeType": "gp3",
                "DeleteOnTermination": True
            }
        }
    ],
    "UserData": base64.b64encode(
        b"#!/bin/bash\ndocker run -p 80:80 877346214550.dkr.ecr.ap-southeast-1.amazonaws.com/messgae:latest"
    ).decode('utf-8')
}

def create_aws_ec2_instance(user_id):
    try:
        if not user_id:
            raise ValueError("User ID is required to create an EC2 instance.")
        
        data = ec2.run_instances(**params)
        if 'Instances' not in data or not data['Instances']:
            raise RuntimeError("Failed to create EC2 instance. No instance information returned.")
        
        instance_id = data['Instances'][0]['InstanceId']
        logger.info('EC2 Instance launched: %s', instance_id)
        
        # Tag instance for easy identification and tracking
        ec2.create_tags(
            Resources=[instance_id],
            Tags=[{"Key": "UserId", "Value": str(user_id)}]
        )
        return instance_id  # Return instance ID
    except boto3.exceptions.Boto3Error as boto_err:
        logger.error('AWS SDK error while creating EC2 instance: %s', boto_err)
    except Exception as err:
        logger.error('Error creating EC2 instance: %s', err)
    return None

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

def start_docker_on_ec2_instance(instance_id):
    try:
        if not instance_id:
            raise ValueError("Instance ID is required to start Docker on EC2 instance.")
        
        command = "docker run -p 80:80 877346214550.dkr.ecr.ap-southeast-1.amazonaws.com/messgae:latest"

        ssm_status = ssm.describe_instance_information()
        is_registered = any(info['InstanceId'] == instance_id for info in ssm_status.get('InstanceInformationList', []))
        
        if not is_registered:
            logger.warning("Instance not yet registered with SSM. Retrying...")
            return {"error": "Instance not registered with SSM"}
        
        logger.info("Instance registered with SSM")

        ssm_params = {
            "DocumentName": "AWS-RunShellScript",
            "InstanceIds": [instance_id],
            "Parameters": {"commands": [command]}
        }

        ssm_response = ssm.send_command(**ssm_params)
        if 'Command' not in ssm_response or 'CommandId' not in ssm_response['Command']:
            raise RuntimeError("Failed to send SSM command. No command information returned.")
        
        logger.info('SSM Command triggered: %s', ssm_response)
        return {
            "instanceId": instance_id,
            "ssmCommandId": ssm_response['Command']['CommandId']
        }
    except boto3.exceptions.Boto3Error as boto_err:
        logger.error('AWS SDK error while starting Docker on EC2 instance: %s', boto_err)
    except Exception as err:
        logger.error('Error starting Docker on EC2 instance: %s', err)
    return None
