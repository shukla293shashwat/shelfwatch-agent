"""Generate a standard CloudFormation template from the reviewable bootstrap script."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ref = lambda name: {'Ref': name}
sub = lambda text: {'Fn::Sub': text}

resources = {
    'Vpc': {'Type':'AWS::EC2::VPC','Properties':{'CidrBlock':'10.42.0.0/16','EnableDnsSupport':True,'EnableDnsHostnames':True}},
    'Gateway': {'Type':'AWS::EC2::InternetGateway'},
    'GatewayAttachment': {'Type':'AWS::EC2::VPCGatewayAttachment','Properties':{'VpcId':ref('Vpc'),'InternetGatewayId':ref('Gateway')}},
    'Subnet': {'Type':'AWS::EC2::Subnet','Properties':{'VpcId':ref('Vpc'),'CidrBlock':'10.42.1.0/24','MapPublicIpOnLaunch':True}},
    'Routes': {'Type':'AWS::EC2::RouteTable','Properties':{'VpcId':ref('Vpc')}},
    'InternetRoute': {'Type':'AWS::EC2::Route','DependsOn':'GatewayAttachment','Properties':{'RouteTableId':ref('Routes'),'DestinationCidrBlock':'0.0.0.0/0','GatewayId':ref('Gateway')}},
    'RouteAssociation': {'Type':'AWS::EC2::SubnetRouteTableAssociation','Properties':{'SubnetId':ref('Subnet'),'RouteTableId':ref('Routes')}},
    'Firewall': {'Type':'AWS::EC2::SecurityGroup','Properties':{'GroupDescription':'HTTPS demo; no public SSH or Python port','VpcId':ref('Vpc'),
        'SecurityGroupIngress':[{'IpProtocol':'tcp','FromPort':port,'ToPort':port,'CidrIp':'0.0.0.0/0'} for port in (80,443)],
        'SecurityGroupEgress':[{'IpProtocol':'tcp','FromPort':port,'ToPort':port,'CidrIp':'0.0.0.0/0'} for port in (80,443)]+[{'IpProtocol':protocol,'FromPort':53,'ToPort':53,'CidrIp':'10.42.0.0/16'} for protocol in ('tcp','udp')]}},
    'AppLogs': {'Type':'AWS::Logs::LogGroup','Properties':{'RetentionInDays':1}},
    'ServerRole': {'Type':'AWS::IAM::Role','Properties':{
        'AssumeRolePolicyDocument':{'Version':'2012-10-17','Statement':[{'Effect':'Allow','Principal':{'Service':'ec2.amazonaws.com'},'Action':'sts:AssumeRole'}]},
        
        'Policies':[{'PolicyName':'DemoResources','PolicyDocument':{'Version':'2012-10-17','Statement':[
            {'Effect':'Allow','Action':['ssm:UpdateInstanceInformation','ssmmessages:CreateControlChannel','ssmmessages:CreateDataChannel','ssmmessages:OpenControlChannel','ssmmessages:OpenDataChannel'],'Resource':'*'},
            {'Effect':'Allow','Action':['s3:GetObject'],'Resource':sub('arn:${AWS::Partition}:s3:::${SourceBucket}/${SourceKey}')},
            {'Effect':'Allow','Action':['ssm:GetParameter'],'Resource':sub('arn:${AWS::Partition}:ssm:${AWS::Region}:${AWS::AccountId}:parameter${TokenParameter}')},
            {'Effect':'Allow','Action':['logs:CreateLogStream','logs:DescribeLogStreams','logs:PutLogEvents'],'Resource':{'Fn::GetAtt':['AppLogs','Arn']}},
            {'Effect':'Allow','Action':['cloudformation:SignalResource'],'Resource':sub('arn:${AWS::Partition}:cloudformation:${AWS::Region}:${AWS::AccountId}:stack/${AWS::StackName}/*')},
        ]}}]}},
    'ServerProfile': {'Type':'AWS::IAM::InstanceProfile','Properties':{'Roles':[ref('ServerRole')]}},
    'Server': {'Type':'AWS::EC2::Instance','DependsOn':['InternetRoute','RouteAssociation'],
        'CreationPolicy':{'ResourceSignal':{'Count':1,'Timeout':'PT30M'}},
        'Properties':{'ImageId':ref('Ami'),'InstanceType':ref('InstanceType'),
            'IamInstanceProfile':ref('ServerProfile'),'InstanceInitiatedShutdownBehavior':'terminate',
            'MetadataOptions':{'HttpTokens':'required','HttpPutResponseHopLimit':1},
            'BlockDeviceMappings':[{'DeviceName':'/dev/xvda','Ebs':{'Encrypted':True,'DeleteOnTermination':True,'VolumeSize':12,'VolumeType':'gp3'}}],
            'NetworkInterfaces':[{'DeviceIndex':'0','AssociatePublicIpAddress':True,'SubnetId':ref('Subnet'),'GroupSet':[ref('Firewall')]}],
            'Tags':[{'Key':'Name','Value':'ShelfWatch disposable demo'},{'Key':'Project','Value':'ShelfWatch'}],
            'UserData':{'Fn::Base64':sub((HERE/'bootstrap.sh').read_text(encoding='utf-8-sig'))}}},
}
template = {'AWSTemplateFormatVersion':'2010-09-09','Description':'ShelfWatch: OpenCV 5 on EC2, HTTPS, private state, scoped IAM and short-retention logs.',
    'Parameters':{
        'Ami':{'Type':'AWS::SSM::Parameter::Value<AWS::EC2::Image::Id>','Default':'/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64'},
        'InstanceType':{'Type':'String','Default':'t3.small','AllowedValues':['t3.micro','t3.small']},
        'SourceBucket':{'Type':'String','AllowedPattern':'[a-z0-9.-]{3,63}'},
        'SourceKey':{'Type':'String','Default':'source.zip'},
        'SourceSha256':{'Type':'String','AllowedPattern':'[0-9a-f]{64}'},
        'TokenParameter':{'Type':'String','AllowedPattern':'/shelfwatch/[A-Za-z0-9_-]+/access-code'},
        'DemoLifetimeHours':{'Type':'Number','Default':72,'MinValue':1,'MaxValue':168},
    },'Resources':resources,
    'Outputs':{'DemoUrl':{'Value':sub('https://${Server.PublicIp}.sslip.io')},'InstanceId':{'Value':ref('Server')},'LogGroup':{'Value':ref('AppLogs')}}}
(HERE/'template.json').write_text(json.dumps(template,indent=2),encoding='utf-8')
print('Generated',HERE/'template.json')
