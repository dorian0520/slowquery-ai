"""실제 ASL의 JSONPath·단계 전달·실패 분기를 로컬 대역으로 검사한다.

AWS 서비스 에뮬레이터가 아니다. Retry 대기·AWS IAM·타임아웃은 실제 서비스 검사와 별개다.
"""
import copy,json,re
from pathlib import Path
import pytest
ASL=json.loads((Path(__file__).parents[1]/'statemachine/daily.asl.json').read_text())

class Failed(Exception):pass


def path(data,key):
    if key=='$':return data
    for part in key[2:].split('.'):data=data[part]
    return data


def resolve(template,data,item=None):
    if not isinstance(template,dict):return template
    out={}
    for k,v in template.items():
        if k.endswith('.$'):
            out[k[:-2]]=item if v=='$$.Map.Item.Value' else path(data,v)
        else:out[k]=resolve(v,data,item)
    return out


def run_scope(definition,data,invoke,seen):
    states=definition['States'];name=definition['StartAt'];data=copy.deepcopy(data)
    for _ in range(100):
        st=states[name];seen.append(name);kind=st['Type']
        if kind=='Succeed':return data
        if kind=='Fail':raise Failed(name)
        if kind=='Choice':
            name=next((c['Next'] for c in st['Choices'] if path(data,c['Variable'])==c['BooleanEquals']),st['Default']);continue
        try:
            if kind=='Task':
                params=st['Parameters'];fn=re.search(r'\$\{(\w+)\}',params['FunctionName']).group(1) if 'FunctionName' in params else 'sns'
                payload=path(data,params['Payload.$']) if 'Payload.$' in params else resolve(params.get('Payload',{}),data) if 'Payload' in params else data
                output=invoke(fn,payload)
                result=resolve(st['ResultSelector'],{'Payload':output}) if 'ResultSelector' in st else output
            elif kind=='Map':
                result=[run_scope(st['ItemProcessor'],resolve(st['ItemSelector'],data,item),invoke,seen) for item in path(data,st['ItemsPath'])]
            else:result=resolve(st['Parameters'],data) if 'Parameters' in st else st.get('Result',data)
            where=st.get('ResultPath','$')
            if where=='$':data=result
            elif where is not None:data[where[2:]]=result
        except (KeyError,AssertionError):raise  # 전달 계약 오류를 서비스 실패로 가리지 않는다
        except Exception:
            caught=next((c for c in st.get('Catch',[]) if 'States.ALL' in c['ErrorEquals']),None)
            if not caught:raise
            data[caught['ResultPath'][2:]]={'Error':'InjectedFailure'};name=caught['Next'];continue
        if st.get('End'):return data
        name=st['Next']
    raise AssertionError('unbounded state loop')


def scenario(weekly=False,fail=()):
    seen=[];calls=[]
    def invoke(fn,payload):
        calls.append(fn)
        if fn in fail:raise RuntimeError('injected')
        if fn=='collect_arn':return {'log_date':'2026-10-12','weekly':weekly,'collected':{'shop-db':1},'failed':[]}
        if fn=='detect_arn':assert payload['log_date']=='2026-10-12';return {'count':1,'hits':[{'qhash':'q'}]}
        if fn=='issue_tickets_arn':assert payload['hits'][0]['qhash']=='q';return {'candidates':[{'ticket_id':1,'log_date':'2026-10-12'}]}
        if fn=='analyze_arn':assert payload['ticket']['ticket_id']==1;return {'status':'OK','ticket_id':1}
        if fn=='verify_arn':assert payload['analysis']['status'] in ('OK','ERROR');return {'status':'PASS'}
        if fn=='attach_arn':assert payload['verify']['status'] in ('PASS','ERROR');return {'note':'review'}
        return {}
    return invoke,seen,calls


def test_weekly_and_nonweekly_paths():
    for weekly in (False,True):
        invoke,seen,calls=scenario(weekly);run_scope(ASL,{},invoke,seen)
        assert ('Report' in seen)==weekly and seen[-1]=='Done'
        assert calls.count('analyze_arn')==1


@pytest.mark.parametrize('failure',['analyze_arn','verify_arn','attach_arn'])
def test_per_ticket_failure_continues(failure):
    invoke,seen,calls=scenario(fail=[failure]);run_scope(ASL,{},invoke,seen)
    assert seen[-1]=='Done' and 'Track' in seen


@pytest.mark.parametrize('failure',['collect_arn','detect_arn','issue_tickets_arn','track_arn','report_arn'])
def test_pipeline_failure_remains_failed_even_if_sns_fails(failure):
    invoke,seen,calls=scenario(weekly=True,fail=[failure,'sns'])
    with pytest.raises(Failed):run_scope(ASL,{},invoke,seen)
    assert seen[-1]=='Failed'


def test_publish_and_sns_failure_still_runs_weekly_report():
    invoke,seen,calls=scenario(weekly=True,fail=['publish_arn','sns']);run_scope(ASL,{},invoke,seen)
    assert 'NotifyPublishFailure' in seen and 'Report' in seen and seen[-1]=='Done'
