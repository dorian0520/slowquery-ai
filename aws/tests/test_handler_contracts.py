"""핸들러 경계: 입력 오류, 연결 정리, 마스킹 및 상태 전달."""
import json
import pytest
from slowq_aws import common, collect, issue_tickets, track, init_db, tools, analyze, publish, attach, report
from test_publish import CFG,TICKET


def test_tls_missing_ca_refuses_connection(monkeypatch):
    monkeypatch.setattr(common.os.path,'exists',lambda p:False)
    with pytest.raises(RuntimeError,match='CA'):common.ssl_options()


@pytest.mark.parametrize('event',[{'only':'other'},{'reset_shop':'false'}])
def test_init_invalid_input_never_connects(event,monkeypatch):
    monkeypatch.setattr(common,'connect',lambda *a,**k:pytest.fail('invalid input connected'))
    with pytest.raises(init_db.InitError):init_db.handler(event,None)


def test_collect_all_failed_raises_and_closes(fake_conn,monkeypatch):
    store=fake_conn(rules=[('FROM cmdb_cluster',[{'cluster':'a','host':'h','port':3306}])])
    monkeypatch.setenv('COLLECTOR_SECRET_ARN','s');monkeypatch.setattr(common,'store_conn',lambda:store)
    def fail(*args,**kwargs):raise OSError('unavailable')
    monkeypatch.setattr(common,'connect',fail)
    with pytest.raises(RuntimeError,match='모든 클러스터'):collect.handler({'log_date':'2026-10-12'},None)
    assert store.closed


def test_issue_handler_returns_candidate_contract(fake_conn,monkeypatch):
    row={'ticket_id':3,'cluster':'shop-db','qhash':'q','query_text':'SELECT 1'}
    store=fake_conn(rules=[('SELECT t.ticket_id',[row])]);monkeypatch.setattr(common,'store_conn',lambda:store)
    monkeypatch.setattr(issue_tickets.stickets,'issue',lambda *a:[{'ticket_id':3}])
    out=issue_tickets.handler({'log_date':'2026-10-12','hits':[]},None)
    assert out['candidates'][0]['log_date']=='2026-10-12' and out['made'][0]['ticket_id']==3 and store.closed


def test_track_handler_translates_changed_statuses(fake_conn,monkeypatch):
    store=fake_conn();monkeypatch.setattr(common,'store_conn',lambda:store)
    monkeypatch.setattr(track.stickets,'track',lambda *args:[(7,'RESOLVED','REOPENED')])
    assert track.handler({'log_date':'2026-10-12'},None)['changed']==[{'ticket_id':7,'from':'RESOLVED','to':'REOPENED'}]
    assert store.closed


def test_tools_mask_stored_query_and_schema_defaults(fake_conn):
    store=fake_conn(rules=[('FROM slow_digest_daily',[{'query_text':"SELECT * FROM users WHERE email='private@example.com' AND user_id=42"}])])
    shop=fake_conn(rules=[('SHOW CREATE',[{'Create Table':"CREATE TABLE users(email varchar(100) DEFAULT 'private@example.com')"}]),('SHOW INDEX',[])])
    t=tools.Tools(store,shop,'shop-db')
    assert 'private@example.com' not in json.dumps(t.top_queries('2026-10-12'))
    assert 'private@example.com' not in t.table_info('users')['ddl']


def test_tools_do_not_forward_db_error_values(fake_conn):
    shop=fake_conn(fail=[('EXPLAIN',RuntimeError('password or actual query value'))])
    out,error=tools.Tools(fake_conn(),shop,'c').call('explain',{'sql':'SELECT 1'})
    assert error and 'password' not in json.dumps(out)


def test_jira_checkpoint_precedes_slack_failure(fake_conn):
    store=fake_conn(rules=[('FROM tuning_ticket t JOIN cmdb_cluster',[TICKET])]);calls=[]
    def post(url,body,headers):
        calls.append(url)
        if 'slack' in url:
            assert any(sql.startswith('INSERT INTO ticket_event') for sql in store.sqls())
            raise RuntimeError('temporary failure')
        return {'key':'SLOWQ-1'}
    out=publish.publish(store,'2026-10-12',CFG,False,'',post=post)
    assert out['sent']==[1] and len([sql for sql in store.sqls() if sql.startswith('INSERT INTO ticket_event')])==1


@pytest.mark.parametrize('days',[0,367,-1])
def test_report_invalid_window_never_connects(days,monkeypatch):
    monkeypatch.setattr(common,'store_conn',lambda:pytest.fail('invalid input connected'))
    with pytest.raises(ValueError):report.handler({'log_date':'2026-10-12','days':days},None)


def test_common_tls_secret_connection_contract(fake_conn,monkeypatch,tmp_path):
    ca=tmp_path/'ca.pem';ca.write_text('test CA');monkeypatch.setattr(common,'CA_BUNDLE',str(ca));monkeypatch.setattr(common,'_secret_cache',{})
    reads=[]
    class SM:
        def get_secret_value(self,**kwargs):reads.append(kwargs);return {'SecretString':json.dumps({'username':'u','password':'p'})}
    monkeypatch.setattr(common,'secrets_client',lambda:SM());made=[]
    def connect(**kwargs):made.append(kwargs);return fake_conn()
    monkeypatch.setattr(common.pymysql,'connect',connect)
    common.connect('h','s','dba');common.connect('h','s','shop')
    assert len(reads)==1 and made[0]['ssl']['ca']==str(ca) and made[0]['database']=='dba' and made[1]['database']=='shop'
    assert common.jsonable({'n':dt_decimal('1.5')})=={'n':1.5}


def dt_decimal(s):
    from decimal import Decimal
    return Decimal(s)


def test_init_handler_separates_target_and_verify_permissions(fake_conn,monkeypatch):
    target,verify=fake_conn(),fake_conn();applied=[]
    for key in ('TARGET_HOST','VERIFY_HOST','TARGET_MASTER_SECRET_ARN','VERIFY_MASTER_SECRET_ARN','COLLECTOR_SECRET_ARN','STORE_SECRET_ARN','AI_SECRET_ARN','GRAFANA_SECRET_ARN','WORKLOAD_SECRET_ARN','VERIFY_SECRET_ARN'):monkeypatch.setenv(key,key.lower())
    monkeypatch.setattr(init_db,'master_conn',lambda host,secret:target if host=='target_host' else verify)
    monkeypatch.setattr(init_db,'load_sample',lambda *a:'skip (이미 있음)')
    monkeypatch.setattr(init_db,'apply_schema',lambda conn,path:applied.append((conn,path)))
    monkeypatch.setattr(common,'get_secret',lambda arn:{'username':arn,'password':'test-only-password'})
    result=init_db.handler({},None)
    assert set(result)=={'target','verify'} and target.closed and verify.closed
    assert len(applied)==1 and applied[0][0] is target
    assert all('`shop`.*' in sql for sql in verify.sqls() if sql.startswith('GRANT'))
    assert not any('ALTER, INDEX' in sql for sql in target.sqls())


def test_init_timeout_does_not_start_second_sample(fake_conn,monkeypatch):
    for key in ('TARGET_HOST','VERIFY_HOST','TARGET_MASTER_SECRET_ARN','VERIFY_MASTER_SECRET_ARN'):monkeypatch.setenv(key,'x')
    conn=fake_conn();monkeypatch.setattr(init_db,'master_conn',lambda *a:conn);monkeypatch.setattr(init_db,'load_sample',lambda *a:'created');monkeypatch.setattr(init_db,'accounts',lambda *a:[]);monkeypatch.setattr(init_db,'apply_schema',lambda *a:None)
    class Context:
        def get_remaining_time_in_millis(self):return 100000
    result=init_db.handler({},Context())
    assert '시간 부족' in result['verify'] and conn.closed


def test_workload_handler_scopes_queries_and_closes(fake_conn,monkeypatch):
    from slowq_aws import workload
    conn=fake_conn();monkeypatch.setenv('TARGET_HOST','h');monkeypatch.setenv('WORKLOAD_SECRET_ARN','s');monkeypatch.setattr(common,'connect',lambda *a,**k:conn)
    out=workload.handler({'only':['order_by_pk'],'scale':0.01},None)
    assert out=={'order_by_pk':3} and conn.closed
    assert all('WHERE order_id' in sql for sql in conn.sqls())


def test_detect_handler_returns_truncation_count(fake_conn,monkeypatch):
    from slowq_aws import detect
    conn=fake_conn();monkeypatch.setattr(common,'store_conn',lambda:conn);monkeypatch.setattr(detect.sdetect,'run',lambda *a:[])
    assert detect.handler({'log_date':'2026-10-12'},None)=={'log_date':'2026-10-12','count':0,'truncated':0,'hits':[]}
    assert conn.closed


def test_attach_handler_failed_verification_never_marks_verified(fake_conn,monkeypatch):
    conn=fake_conn();monkeypatch.setattr(common,'store_conn',lambda:conn)
    attach.handler({'ticket':{'ticket_id':3,'log_date':'2026-10-12'},'analysis':{'status':'ERROR'},'verify':{'status':'ERROR'}},None)
    assert conn.closed and next(args for sql,args in conn.executed if sql.startswith('UPDATE tuning_ticket'))[1]==0


def test_verify_handler_closes_on_measurement_failure(fake_conn,monkeypatch):
    from slowq_aws import verify
    conn=fake_conn();monkeypatch.setenv('VERIFY_HOST','h');monkeypatch.setenv('VERIFY_SECRET_ARN','s');monkeypatch.setattr(common,'connect',lambda *a,**k:conn)
    def fail(*a,**k):raise RuntimeError('measurement failed')
    monkeypatch.setattr(verify,'run',fail)
    with pytest.raises(RuntimeError):verify.handler({'analysis':{'ticket_id':1,'status':'OK','proposal':{'proposal':'ALTER TABLE orders ADD INDEX ix_u (user_id)','test_sql':'SELECT 1'}}},None)
    assert conn.closed
