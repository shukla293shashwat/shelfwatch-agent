"""HTTP checks for access control, upload validation, ROI, and durable approval."""
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ApiChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.previous = {name: os.environ.get(name) for name in ('SHELFWATCH_TOKEN','SHELFWATCH_STATE_DIR','SHELFWATCH_PUBLIC')}
        cls.token = secrets.token_urlsafe(24)
        os.environ.update(SHELFWATCH_TOKEN=cls.token, SHELFWATCH_STATE_DIR=cls.directory.name, SHELFWATCH_PUBLIC='1')
        with socket.socket() as connection:
            connection.bind(('127.0.0.1',0))
            port = connection.getsockname()[1]
        cls.base = f'http://127.0.0.1:{port}'
        environment = os.environ.copy()
        environment.update(HOST='127.0.0.1', PORT=str(port), PYTHONDONTWRITEBYTECODE='1')
        cls.process = subprocess.Popen([sys.executable, '-B', 'run.py'], cwd=ROOT,
                                       env=environment, stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL)
        for _ in range(100):
            try:
                with urllib.request.urlopen(cls.base + '/health', timeout=1) as response:
                    if response.status == 200:
                        return
            except (OSError, urllib.error.URLError):
                time.sleep(.1)
        raise RuntimeError('The test server did not start.')

    @classmethod
    def tearDownClass(cls):
        if cls.process.poll() is None:
            if os.name == 'nt':
                subprocess.run(['taskkill', '/PID', str(cls.process.pid), '/T', '/F'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                cls.process.terminate()
            cls.process.wait(timeout=10)
        for name,value in cls.previous.items():
            if value is None:
                os.environ.pop(name,None)
            else:
                os.environ[name]=value
        cls.directory.cleanup()

    def request(self,path,data=None,authorized=True,headers=None):
        merged = {'Authorization':'Bearer '+self.token} if authorized else {}
        merged.update(headers or {})
        request = urllib.request.Request(self.base+path,data=data,headers=merged)
        try:
            with urllib.request.urlopen(request,timeout=20) as response:
                return response.status,response.read(),dict(response.headers)
        except urllib.error.HTTPError as error:
            return error.code,error.read(),dict(error.headers)

    def upload(self,current,reference,fields=None):
        boundary = 'ShelfWatchTest'+secrets.token_hex(8)
        body=bytearray()
        for field,path in [('current',current),('reference',reference)]:
            body.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; filename="photo.png"\r\nContent-Type: image/png\r\n\r\n'.encode())
            body.extend(path.read_bytes() if isinstance(path,Path) else path)
            body.extend(b'\r\n')
        for field,value in (fields or {}).items():
            body.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"\r\n\r\n{value}\r\n'.encode())
        body.extend(f'--{boundary}--\r\n'.encode())
        return self.request('/analyze',bytes(body),headers={'Content-Type':'multipart/form-data; boundary='+boundary})

    def test_health_and_assets(self):
        status,body,headers=self.request('/health',authorized=False)
        self.assertEqual(status,200)
        self.assertTrue(json.loads(body)['auth_required'])
        self.assertIn('x-request-id',{name.lower() for name in headers})
        for path in ('/','/static/app.js','/static/styles.css','/examples/reference.jpg'):
            self.assertEqual(self.request(path,authorized=False)[0],200)

    def test_access_code_required(self):
        self.assertEqual(self.request('/demo',b'',authorized=False)[0],401)
        self.assertEqual(self.request('/orders',authorized=False)[0],401)
        self.assertEqual(self.request('/metrics',authorized=False)[0],401)

    def test_upload_validation(self):
        reference=ROOT/'samples/reference.jpg'
        self.assertEqual(self.upload(b'not an image',reference)[0],400)
        self.assertEqual(self.upload(b'',reference)[0],400)
        self.assertEqual(self.upload(reference,reference,{'roi':'[0.9,0,0.1,1]'})[0],400)
        self.assertEqual(self.upload(reference,reference,{'rows':'0'})[0],400)
        self.assertEqual(self.request('/demo',b'',headers={'Content-Length':str(30*1024*1024)})[0],413)

    def test_real_photo_localization(self):
        source=ROOT/'samples/external/shelfchange3d'
        for number in (1,2):
            status,body,_=self.upload(source/f'demo{number}_t1.png',source/f'demo{number}_t0.png')
            result=json.loads(body)
            self.assertEqual(status,200)
            self.assertEqual(result['gaps'],[[1,3]])
            self.assertTrue(result['regions'])
            self.assertTrue(any(step['event']=='active_reinspection' for step in result['trace']))

    def test_selection_excludes_changes_outside_shelf(self):
        samples=ROOT/'samples/validation'
        status,body,_=self.upload(samples/'73_change_outside_roi.jpg',samples/'reference_73.jpg',{'roi':'[0,0,1,0.6666666666666666]','rows':'2','cols':'6'})
        self.assertEqual(status,200)
        self.assertEqual(json.loads(body)['status'],'shelf_ok')

    def test_approval_persists_and_cannot_be_repeated(self):
        status,body,_=self.request('/demo',b'')
        result=json.loads(body)
        self.assertEqual(status,200)
        order_id=result['order_id']
        status,body,_=self.request('/approve/'+order_id,b'')
        self.assertEqual(status,200)
        self.assertFalse(json.loads(body)['sent'])
        self.assertEqual(self.request('/approve/'+order_id,b'')[0],404)
        from shelfwatch import storage
        self.assertTrue(any(order['id']==order_id and order['approved_at'] for order in storage.recent_orders()))
        self.assertTrue((Path(self.directory.name)/'shelfwatch.sqlite3').exists())


if __name__=='__main__':
    unittest.main(verbosity=2)

