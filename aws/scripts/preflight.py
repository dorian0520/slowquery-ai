#!/usr/bin/env python3
"""Read-only deployment-account and deletion-permission preflight.

IAM simulation does not replace real organization/SCP, service, or resource-policy checks.
Requires local boto3. Does not fetch secrets, create resources, or alter permissions.
"""
import argparse,json,re
import boto3


def deletion_checks(iam,role_arn,account,region,prefix):
    resources=[( 'rds:DeleteDBInstance',f'arn:aws:rds:{region}:{account}:db:{prefix}-shop-db'),
               ( 'rds:DeleteDBInstance',f'arn:aws:rds:{region}:{account}:db:{prefix}-order-db')]
    out=[]
    for action,resource in resources:
        r=iam.simulate_principal_policy(PolicySourceArn=role_arn,ActionNames=[action],ResourceArns=[resource])['EvaluationResults'][0]
        out.append({'action':action,'decision':r['EvalDecision'],'missing_context':r.get('MissingContextValues',[])})
    return out


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--profile');p.add_argument('--region',default='ap-northeast-2');p.add_argument('--expected-account',required=True);p.add_argument('--prefix',required=True);a=p.parse_args()
    if not re.fullmatch(r'[0-9]{12}',a.expected_account):p.error('예상 계정 ID는 12자리여야 합니다.')
    if not re.fullmatch(r'[a-z][a-z0-9-]{1,20}',a.prefix):p.error('접두어는 소문자로 시작하는 2~21자의 소문자·숫자·하이픈이어야 합니다.')
    session=boto3.Session(profile_name=a.profile,region_name=a.region);who=session.client('sts').get_caller_identity()
    if who['Account']!=a.expected_account:p.error('인증 계정이 예상 계정과 다릅니다. 배포하지 마세요.')
    arn=who['Arn'];iam=session.client('iam')
    if ':assumed-role/' in arn:
        role=arn.split(':assumed-role/',1)[1].split('/')[0];role_arn=iam.get_role(RoleName=role)['Role']['Arn']
    elif ':role/' in arn:role_arn=arn
    else:p.error('이 도구는 역할 인증의 사전 검사를 지원합니다. 승인된 역할을 확인하세요.')
    checks=deletion_checks(iam,role_arn,who['Account'],a.region,a.prefix)
    approved=all(x['decision']=='allowed' and not x['missing_context'] for x in checks)
    print(json.dumps({'account_matches':True,'rds_delete_simulation_allowed':approved,'checks':checks,'actual_delete_tested':False,'limitations':'IAM 시뮬레이션만으로 SCP·리소스 정책·태그 조건과 실제 삭제를 보장하지 않습니다. 오류·누락 컨텍스트가 있으면 배포 전에 확인하세요.'},ensure_ascii=False,indent=2))
    return 0 if approved else 1
if __name__=='__main__':raise SystemExit(main())
