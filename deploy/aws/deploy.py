"""Deploy from a local AWS CLI session; never accepts passwords or static keys."""
import argparse
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile')
    parser.add_argument('--region',default='ap-south-1')
    args=parser.parse_args()
    candidate=Path(os.getenv('LOCALAPPDATA',''))/'Programs/Amazon/AWSCLIV2/aws.exe'
    executable=shutil.which('aws') or (str(candidate) if candidate.is_file() else None)
    if not executable:
        raise SystemExit('Install the official AWS CLI v2 and run aws login first.')
    common=[executable,'--no-cli-pager']
    if args.profile:
        common += ['--profile',args.profile]

    def aws(*command,region=None):
        result=subprocess.run(common+list(command)+['--region',region or args.region,'--output','json'],capture_output=True,text=True)
        if result.returncode:
            raise RuntimeError(result.stderr.strip())
        return json.loads(result.stdout) if result.stdout.strip() else {}

    def json_request(command,payload):
        # Pass secrets through a short-lived local file, not command arguments or logs.
        with tempfile.NamedTemporaryFile('w',suffix='.json',delete=False,encoding='utf-8') as file:
            json.dump(payload,file)
            temporary=Path(file.name)
        try:
            return aws(*command,'--cli-input-json','file://'+str(temporary))
        finally:
            temporary.unlink(missing_ok=True)

    plan=aws('freetier','get-account-plan-state',region='us-east-1')
    gate=subprocess.run([sys.executable,str(ROOT/'deploy/aws/check_free_plan.py')],input=json.dumps(plan),text=True,capture_output=True)
    print(gate.stdout.strip(),flush=True)
    if gate.returncode:
        raise SystemExit(gate.stderr.strip())
    # Read-only probe catches pending service activation before any resources exist.
    aws('ec2','describe-vpcs','--max-results','5')
    state_path=ROOT/'deployment-state.json'
    if state_path.exists():
        raise SystemExit('Existing deployment-state.json found. Review/clean up it before deploying again.')
    account=aws('sts','get-caller-identity')['Account']
    suffix=secrets.token_hex(5)
    state={'region':args.region,'stack':'shelfwatch-demo','bucket':f'shelfwatch-{account}-{suffix}',
           'token_parameter':f'/shelfwatch/{suffix}/access-code','created_resources':[]}

    def save_state():
        state_path.write_text(json.dumps(state,indent=2),encoding='utf-8')

    save_state()
    create=['s3api','create-bucket','--bucket',state['bucket']]
    if args.region!='us-east-1':
        create += ['--create-bucket-configuration','LocationConstraint='+args.region]
    aws(*create)
    state['created_resources'].append('source_bucket');save_state()
    json_request(['s3api','put-public-access-block'],{'Bucket':state['bucket'],'PublicAccessBlockConfiguration':dict.fromkeys(['BlockPublicAcls','IgnorePublicAcls','BlockPublicPolicy','RestrictPublicBuckets'],True)})
    json_request(['s3api','put-bucket-encryption'],{'Bucket':state['bucket'],'ServerSideEncryptionConfiguration':{'Rules':[{'ApplyServerSideEncryptionByDefault':{'SSEAlgorithm':'AES256'}}]}})
    json_request(['ssm','put-parameter'],{'Name':state['token_parameter'],'Type':'SecureString','Value':secrets.token_urlsafe(32)})
    state['created_resources'].append('token_parameter');save_state()
    with tempfile.TemporaryDirectory(prefix='shelfwatch-source-') as folder:
        artifact=Path(folder)/'source.zip'
        subprocess.run([sys.executable,str(ROOT/'scripts/package_release.py'),'--runtime-only','--output',str(artifact)],check=True)
        digest=hashlib.sha256(artifact.read_bytes()).hexdigest()
        aws('s3api','put-object','--bucket',state['bucket'],'--key','source.zip','--body',str(artifact),'--server-side-encryption','AES256')
    state['source_sha256']=digest;save_state()
    subprocess.run([sys.executable,str(ROOT/'deploy/aws/build_template.py')],check=True)
    template='file://'+str(ROOT/'deploy/aws/template.json')
    aws('cloudformation','validate-template','--template-body',template)
    parameters={'SourceBucket':state['bucket'],'SourceKey':'source.zip','SourceSha256':digest,
                'TokenParameter':state['token_parameter'],'InstanceType':'t3.small','DemoLifetimeHours':'72'}
    payload={'StackName':state['stack'],'TemplateBody':(ROOT/'deploy/aws/template.json').read_text(),
             'Capabilities':['CAPABILITY_IAM'],'Parameters':[{'ParameterKey':key,'ParameterValue':value} for key,value in parameters.items()]}
    response=json_request(['cloudformation','create-stack'],payload)
    state['stack_id']=response['StackId'];state['created_resources'].append('stack');save_state()
    print('Creating the AWS stack; this includes the container build and HTTPS check.',flush=True)
    last_status=None
    while True:
        stack=aws('cloudformation','describe-stacks','--stack-name',state['stack'])['Stacks'][0]
        status=stack['StackStatus']
        if status!=last_status:
            print('Stack:',status,flush=True);last_status=status
        if status=='CREATE_COMPLETE':
            state['outputs']={item['OutputKey']:item['OutputValue'] for item in stack.get('Outputs',[])}
            save_state()
            print(json.dumps(state['outputs'],indent=2),flush=True)
            print('The private demo code is in the recorded SSM parameter. No secret was printed.',flush=True)
            return
        if status.endswith(('FAILED','ROLLBACK_COMPLETE')):
            events=aws('cloudformation','describe-stack-events','--stack-name',state['stack'])['StackEvents']
            for event in events:
                if event['ResourceStatus'].endswith('FAILED'):
                    print(event['LogicalResourceId']+': '+event.get('ResourceStatusReason',''),flush=True)
            raise SystemExit('Deployment did not complete. Use the saved state for cleanup; no live URL is claimed.')
        time.sleep(15)


if __name__=='__main__':
    try:
        main()
    except RuntimeError as error:
        raise SystemExit(str(error))
