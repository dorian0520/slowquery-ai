"""Permission preflight must preserve deny and missing context, not assume administrator allows deletion."""
import importlib.util
from pathlib import Path

SPEC=importlib.util.spec_from_file_location('permission_preflight',Path(__file__).resolve().parents[1]/'scripts/preflight.py')
P=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(P)

class IAM:
    def __init__(self,decision,missing=()):self.decision=decision;self.missing=missing;self.requests=[]
    def simulate_principal_policy(self,**request):
        self.requests.append(request)
        return {'EvaluationResults':[{'EvalDecision':self.decision,'MissingContextValues':list(self.missing)}]}

def test_checks_both_exact_test_database_arns():
    iam=IAM('allowed');r=P.deletion_checks(iam,'role','1'*12,'ap-northeast-2','validation')
    assert len(r)==2 and len(iam.requests)==2
    assert iam.requests[0]['ResourceArns']==['arn:aws:rds:ap-northeast-2:'+('1'*12)+':db:validation-shop-db']
    assert iam.requests[1]['ResourceArns']==['arn:aws:rds:ap-northeast-2:'+('1'*12)+':db:validation-order-db']

def test_deny_and_context_are_retained():
    r=P.deletion_checks(IAM('explicitDeny',['aws:MultiFactorAuthPresent']),'role','1'*12,'ap-northeast-2','validation')
    assert all(x['decision']=='explicitDeny' and x['missing_context']==['aws:MultiFactorAuthPresent'] for x in r)
