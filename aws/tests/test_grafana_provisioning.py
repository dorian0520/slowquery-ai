"""Exercise the actual user-data Python renderer against temporary files."""
import configparser,json,re
from pathlib import Path


def test_rpm_file_password_and_json_preserve_special_characters(tmp_path,monkeypatch):
    original_path=Path
    root=tmp_path/'etc/grafana';(root/'secrets').mkdir(parents=True);(root/'provisioning/datasources').mkdir(parents=True)
    (root/'grafana.ini').write_text('[security]\nadmin_user = admin\n[paths]\ndata = /var/lib/grafana\n')
    password='a$"\\:secret'
    cert='-----BEGIN CERTIFICATE-----\nabc\n-----END CERTIFICATE-----\n'
    for name,value in [('admin_password','admin-only'),('ds_password',password),('ds_username','reader'),('rds-ca.pem',cert)]:
        (root/'secrets'/name).write_text(value)
    template=(original_path(__file__).resolve().parents[1]/'grafana/user_data.sh.tftpl').read_text()
    renderer=re.search(r"python3 - <<'PYCONFIG'\n(.*?)\nPYCONFIG",template,re.S).group(1)
    def redirected(value):
        assert str(value).startswith('/etc/grafana/');return tmp_path/str(value).lstrip('/')
    monkeypatch.setattr('pathlib.Path',redirected)
    exec(compile(renderer,'user_data_renderer','exec'),{})
    document=json.loads((root/'provisioning/datasources/slowq.yml').read_text());data=document['datasources'][0]
    assert data['secureJsonData']['password']==password.replace('$','$$')
    assert data['secureJsonData']['tlsCACert']==cert.strip()
    assert data['jsonData']['tlsSkipVerify'] is False
    cfg=configparser.ConfigParser(interpolation=None);cfg.read(root/'grafana.ini')
    assert cfg['security']['admin_password']=='$__file{/etc/grafana/secrets/admin_password}'
    assert cfg['paths']['data']=='/var/lib/grafana'
