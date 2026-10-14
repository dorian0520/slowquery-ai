"""전체 소스 검토에서 발견한 오류의 재현. 실제 AWS/DB/외부 전송 없음."""
import datetime as dt
import json
import pytest
from slowq_aws import analyze, attach, common, detect, publish, report
from test_publish import TICKET
from test_analyze import ITEM, GOOD, FakeBedrock, tool_resp, text_resp


def test_historical_report_queries_requested_period(fake_conn, monkeypatch):
    conn=fake_conn();monkeypatch.setattr(common,'store_conn',lambda:conn);monkeypatch.setenv('REPORT_BUCKET','b')
    class S3:
        def put_object(self,**kw):pass
    report.handler({'log_date':'2020-01-07','days':7},None,s3=S3())
    sql,args=next((sql,args) for sql,args in conn.executed if 'FROM slow_digest_daily' in sql)
    assert 'CURDATE' not in sql
    assert args==(dt.date(2020,1,1),dt.date(2020,1,7))


def test_slack_only_failure_is_not_published(fake_conn):
    conn=fake_conn(rules=[('FROM tuning_ticket t JOIN cmdb_cluster',[TICKET])])
    def post(*args,**kwargs):return {'ok':False,'error':'channel_not_found'}
    out=publish.publish(conn,'2026-10-12',{'slack_bot_token':'test-only-token'},False,'',post=post)
    assert out['errors'] and not out['sent']
    assert not any(sql.startswith('INSERT INTO ticket_event') for sql in conn.sqls())


def test_detect_budget_includes_multibyte_json():
    hits=[{'cluster':'c','qhash':str(i),'exec_cnt':1,'total_sec':1,'avg_sec':1,'reasons':['기준초과'],'query_text':'가'*400} for i in range(200)]
    compact=detect.compact(hits)
    assert len(json.dumps(compact,ensure_ascii=False).encode())<=80*1024
    assert compact and len(compact)<200


def test_tool_calls_have_total_budget(fake_conn):
    class Tools:
        def __init__(self):self.calls=0
        def call(self,*args):self.calls+=1;return {},False
    t=Tools();response=tool_resp('query_trend',{'qhash':ITEM['qhash']});response['output']['message']['content']*=20
    r=analyze.analyze(ITEM,FakeBedrock([response,text_resp(json.dumps(GOOD))]),t,'m')
    assert r['status']=='NO_ANSWER' and t.calls<=16


def test_analyze_closes_first_connection_if_second_fails(fake_conn,monkeypatch):
    conn=fake_conn();calls=iter([conn,None])
    def connect(*args,**kwargs):
        got=next(calls)
        if got is None:raise RuntimeError('second connection unavailable')
        return got
    monkeypatch.setattr(common,'connect',connect);monkeypatch.setenv('TARGET_HOST','h');monkeypatch.setenv('AI_SECRET_ARN','x')
    with pytest.raises(RuntimeError):analyze.handler(ITEM,None)
    assert conn.closed


def test_attach_preserves_rollback_guard_warning():
    rec,note=attach.recommendation({'status':'OK','proposal':GOOD[0]},{'status':'PASS','rolled_back_by_guard':True})
    assert rec['verify']['rolled_back_by_guard'] is True
    assert rec['verify']['pass'] is False and '되돌리기' in note
