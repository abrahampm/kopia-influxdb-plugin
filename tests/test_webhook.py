import pytest
from kopia_influxdb_webhook_plugin import app


def client():
    app.config['TESTING'] = True
    return app.test_client()

# Test data from logs.txt
SNAPSHOT_HEADERS = {
    'Host': 'kopia.example.com',
    'Instance': 'kopia-test-1 (windows-pc)',
    'Subject': 'Successfully created a snapshot of D:\\User on PC',
    'User-Agent': 'Go-http-client/2.0',
}
SNAPSHOT_BODY = '''Path: D:\TestUser
  Status:      success
  Start:       Fri, 27 Jun 2025 11:32:38 -0400
  Duration:    2.5s
  Size:        154.1 GB
  Files:       70171
  Directories: 6942
Generated at Fri, 27 Jun 2025 21:06:41 -0400 by Kopia 0.20.1.
https://kopia.io/'''

MAINTENANCE_HEADERS = {
    'Host': 'influxdb-webhook-plugin:5000',
    'Instance': 'kopia-instance-1 (sftp-server)',
    'Subject': 'Kopia has encountered an error during Maintenance on f795eeb787a8',
    'User-Agent': 'Go-http-client/1.1',
}
MAINTENANCE_BODY = '''Operation: Scheduled Maintenance
Started:   Fri, 27 Jun 2025 06:35:12 -0400
Finished:  Fri, 27 Jun 2025 11:06:11 -0400 (4h30m59s)
dial tcp 192.168.0.100:22: connect: connection timed out
unable to dial [192.168.0.100:22]: &ssh.ClientConfig{Config:ssh.Config{Rand:io.Reader(nil), RekeyThreshold:0x0, KeyExchanges:[]string(nil), Ciphers:[]string(nil), MACs:[]string(nil)}, User:"kopia", Auth:[]ssh.AuthMethod{(ssh.publicKeyCallback)(0x1894c40)}, HostKeyCallback:(ssh.HostKeyCallback)(0x1891120), BannerCallback:(ssh.BannerCallback)(nil), ClientVersion:"", HostKeyAlgorithms:[]string(nil), Timeout:0}
github.com/kopia/kopia/repo/blob/sftp.getSFTPClient
	/home/runner/work/kopia/kopia/repo/blob/sftp/sftp_storage.go:525
error establishing connecting
error opening connection
unable to complete GetBlobFromPath despite 10 retries
unable to complete GetBlob(kopia.maintenance,0,-1) despite 10 retries
error reading schedule blob
error getting status
unable to determine if maintenance is required
unable to run maintenance
Generated at Fri, 27 Jun 2025 11:06:12 -0400 by Kopia 0.20.1.
https://kopia.io/'''

TEST_HEADERS = {
    'Host': 'influxdb-webhook-plugin:5000',
    'Subject': 'Test Notification',
    'Instance': 'kopia-test-1',
    'User-Agent': 'Go-http-client/1.1',
}
TEST_BODY = '''Kopia Version: **0.20.1**\nBuild Info: **abcdef1**\nGithub Repo: **kopia/kopia**\n'''

@pytest.mark.parametrize("headers, body, expected_code", [
    (SNAPSHOT_HEADERS, SNAPSHOT_BODY, 200),
    (MAINTENANCE_HEADERS, MAINTENANCE_BODY, 200),
    (TEST_HEADERS, TEST_BODY, 200),
])
def test_webhook_all_types(headers, body, expected_code, monkeypatch):
    c = client()
    # Patch influx write to avoid real DB call
    monkeypatch.setattr('kopia_influxdb_webhook_plugin.write_api.write', lambda *a, **kw: None)
    resp = c.post('/webhook', data=body, headers=headers)
    assert resp.status_code == expected_code
    assert resp.json['result'] == 'ok'

# Additional: test error handling

def test_webhook_influxdb_error(monkeypatch):
    c = client()
    monkeypatch.setattr('kopia_influxdb_webhook_plugin.write_api.write', lambda *a, **kw: (_ for _ in ()).throw(Exception('fail')))
    resp = c.post('/webhook', data=SNAPSHOT_BODY, headers=SNAPSHOT_HEADERS)
    assert resp.status_code == 500
    assert 'error' in resp.json

