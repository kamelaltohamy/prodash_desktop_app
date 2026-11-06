import os
import unittest
from pathlib import Path

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR / 'backend'

try:
    from backend.app import app, DB_PATH, ADMIN_API_KEY
    HAS_BACKEND = True
except ImportError:
    HAS_BACKEND = False
    app = None
    DB_PATH = None
    ADMIN_API_KEY = None


@unittest.skipUnless(HAS_BACKEND, "Backend module not present in this workspace")
class BackendTests(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        # Reset default settings for test isolation
        from backend.app import DEFAULT_SETTINGS, update_settings
        update_settings(DEFAULT_SETTINGS)

    def tearDown(self):
        from backend.app import DEFAULT_SETTINGS, update_settings
        update_settings(DEFAULT_SETTINGS)
        # Restore real executable if dist/ProDash.exe exists
        real_exe = ROOT_DIR / 'dist' / 'ProDash.exe'
        target_exe = BACKEND_DIR / 'downloads' / 'ProDash.exe'
        if real_exe.exists():
            import shutil
            shutil.copyfile(str(real_exe), str(target_exe))

    def test_index_page(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('Pro Dash', html)
        self.assertIn('team.qrtoba.com', html)
        self.assertIn('qrtobacom@gmail.com', html)
        self.assertIn('patreon.com/c/altohamy', html)
        # Verify security headers
        self.assertEqual(response.headers.get('X-Frame-Options'), 'DENY')
        self.assertEqual(response.headers.get('X-Content-Type-Options'), 'nosniff')
        self.assertIn("default-src 'self'", response.headers.get('Content-Security-Policy', ''))
        self.assertIn('camera=()', response.headers.get('Permissions-Policy', ''))

    def test_api_info(self):
        response = self.client.get('/api/info')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data['name'], 'Pro Dash')
        self.assertEqual(data['website'], 'https://team.qrtoba.com')
        self.assertEqual(data['email'], 'qrtobacom@gmail.com')
        self.assertEqual(data['patreon'], 'https://www.patreon.com/c/altohamy')

    def test_contact_validation_and_storage(self):
        # Missing fields -> 400
        res = self.client.post('/api/contact', json={'name': 'Ali'})
        self.assertEqual(res.status_code, 400)

        # Invalid email -> 400
        res = self.client.post('/api/contact', json={
            'name': 'Ali',
            'email': 'not-an-email',
            'message': 'Hello'
        })
        self.assertEqual(res.status_code, 400)

        # Honeypot spam test -> returns 200 but drops storage
        res = self.client.post('/api/contact', json={
            'name': 'Bot',
            'email': 'bot@example.com',
            'message': 'Spam message',
            'website_hp': 'http://spam.com'
        })
        self.assertEqual(res.status_code, 200)

        # Successful submission -> 200
        res = self.client.post('/api/contact', json={
            'name': 'Test User',
            'email': 'user@example.com',
            'message': 'Love the app!'
        })
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()['success'])

    def test_inquiries_protection(self):
        # Unauthorized access without token -> 401
        res = self.client.get('/api/inquiries')
        self.assertEqual(res.status_code, 401)

        # Unauthorized access with wrong token -> 401
        res = self.client.get('/api/inquiries', headers={'Authorization': 'Bearer wrong-key'})
        self.assertEqual(res.status_code, 401)

        # Authorized with Bearer header -> 200
        res = self.client.get('/api/inquiries', headers={'Authorization': f'Bearer {ADMIN_API_KEY}'})
        self.assertEqual(res.status_code, 200)
        inquiries = res.get_json()
        self.assertTrue(any(i['name'] == 'Test User' for i in inquiries))
        # Verify bot submission with honeypot was not saved
        self.assertFalse(any(i['name'] == 'Bot' for i in inquiries))

        # Authorized with ?key= query param -> 200
        res = self.client.get(f'/api/inquiries?key={ADMIN_API_KEY}')
        self.assertEqual(res.status_code, 200)

    def test_health(self):
        res = self.client.get('/health')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()['status'], 'healthy')

    def test_download_endpoint(self):
        res = self.client.get('/download')
        exe_path = ROOT_DIR / 'dist' / 'ProDash.exe'
        if exe_path.exists():
            self.assertEqual(res.status_code, 200)
            self.assertIn('ProDash.exe', res.headers.get('Content-Disposition', ''))
            res.close()
        else:
            self.assertEqual(res.status_code, 404)

    def test_admin_login_and_dashboard_flow(self):
        # 0. Decoy /admin route returns 404
        res_decoy = self.client.get('/admin')
        self.assertEqual(res_decoy.status_code, 404)

        # 1. Unauthenticated /pure-admin redirects to /pure-admin/login
        res = self.client.get('/pure-admin')
        self.assertEqual(res.status_code, 302)
        self.assertIn('/pure-admin/login', res.headers['Location'])

        # 2. Login GET returns 200
        res = self.client.get('/pure-admin/login')
        self.assertEqual(res.status_code, 200)

        # 3. Wrong password fails
        res = self.client.post('/pure-admin/login', data={'key': 'wrong-password'})
        self.assertEqual(res.status_code, 200)
        self.assertIn('Invalid Admin Security Key', res.get_data(as_text=True))

        # 4. Correct password logs in and redirects
        res = self.client.post('/pure-admin/login', data={'key': ADMIN_API_KEY})
        self.assertEqual(res.status_code, 302)
        self.assertIn('/pure-admin', res.headers['Location'])

        # 5. Dashboard accessible with session
        res = self.client.get('/pure-admin')
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)
        self.assertIn('Admin Dashboard', html)
        self.assertIn('Social Links', html)
        self.assertIn('ProDash.exe', html)

        # 6. Update settings (social links)
        res = self.client.post('/pure-admin/settings', data={
            'app_name': 'Pro Dash Custom',
            'version': '1.2.0',
            'tagline': 'Updated Tagline',
            'website': 'https://custom.qrtoba.com',
            'email': 'support@qrtoba.com',
            'patreon': 'https://www.patreon.com/c/altohamy_new',
            'github': 'https://github.com/custom',
            'creator_name': 'Kamel Altohamy'
        })
        self.assertEqual(res.status_code, 302)

        # Verify /api/info returns updated settings
        info = self.client.get('/api/info').get_json()
        self.assertEqual(info['version'], '1.2.0')
        self.assertEqual(info['website'], 'https://custom.qrtoba.com')
        self.assertEqual(info['email'], 'support@qrtoba.com')
        self.assertEqual(info['patreon'], 'https://www.patreon.com/c/altohamy_new')

        # 7. Upload new app executable
        from io import BytesIO
        fake_exe = BytesIO(b'MZ-stub-fake-exe-content')
        res = self.client.post('/pure-admin/upload/app', data={
            'app_file': (fake_exe, 'ProDash.exe'),
            'version': '1.2.1'
        })
        self.assertEqual(res.status_code, 302)
        # Verify /download serves the updated uploaded file
        res_dl = self.client.get('/download')
        self.assertEqual(res_dl.status_code, 200)
        self.assertEqual(res_dl.get_data(), b'MZ-stub-fake-exe-content')
        res_dl.close()

        # 8. Upload icon
        fake_icon = BytesIO(b'<svg xmlns="http://www.w3.org/2000/svg"></svg>')
        res = self.client.post('/pure-admin/upload/icon', data={
            'icon_file': (fake_icon, 'pro-dash.svg')
        })
        self.assertEqual(res.status_code, 302)

        # 9. Logout
        res = self.client.get('/pure-admin/logout')
        self.assertEqual(res.status_code, 302)
        # Verify /pure-admin is protected again
        res = self.client.get('/pure-admin')
        self.assertEqual(res.status_code, 302)
        self.assertIn('/pure-admin/login', res.headers['Location'])

    def test_superuser_creation_and_auth(self):
        from backend.app import (
            create_user, get_user_by_username, verify_user_credentials,
            change_user_password, delete_user, list_users
        )
        # 1. Clean any previous test user
        existing = get_user_by_username('testadmin')
        if existing:
            delete_user(existing['id'])

        # 2. Validation tests
        with self.assertRaises(ValueError):
            create_user('a', 'validpassword123')  # Too short username
        with self.assertRaises(ValueError):
            create_user('testadmin', 'short')  # Too short password

        # 3. Create superuser
        user = create_user('testadmin', 'securepass123', is_superuser=True)
        self.assertEqual(user['username'], 'testadmin')
        self.assertTrue(user['is_superuser'])

        # 4. Duplicate creation should fail
        with self.assertRaises(ValueError):
            create_user('testadmin', 'anotherpassword123')

        # 5. Credential verification
        self.assertIsNotNone(verify_user_credentials('testadmin', 'securepass123'))
        self.assertIsNone(verify_user_credentials('testadmin', 'wrongpass'))
        self.assertIsNone(verify_user_credentials('nonexistent', 'securepass123'))

        # 6. Web login with superuser credentials
        res = self.client.post('/pure-admin/login', data={
            'username': 'testadmin',
            'password': 'wrongpassword'
        })
        self.assertEqual(res.status_code, 200)
        self.assertIn('Invalid username or password', res.get_data(as_text=True))

        res = self.client.post('/pure-admin/login', data={
            'username': 'testadmin',
            'password': 'securepass123'
        })
        self.assertEqual(res.status_code, 302)
        self.assertIn('/pure-admin', res.headers['Location'])

        # 7. Check dashboard renders user badge and superuser tab
        res = self.client.get('/pure-admin')
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)
        self.assertIn('testadmin', html)
        self.assertIn('SUPERUSER', html)

        # 8. Password change
        self.assertTrue(change_user_password('testadmin', 'brandnewpass999'))
        self.assertIsNotNone(verify_user_credentials('testadmin', 'brandnewpass999'))
        self.assertIsNone(verify_user_credentials('testadmin', 'securepass123'))

        # 9. Cleanup
        delete_user(user['id'])
        self.assertIsNone(get_user_by_username('testadmin'))

    def test_manage_cli_commands(self):
        import argparse
        from backend.manage import (
            cmd_createsuperuser, cmd_listusers, cmd_changepassword
        )
        from backend.app import get_user_by_username, delete_user

        # Clean if exists
        old = get_user_by_username('clisuper')
        if old:
            delete_user(old['id'])

        # Test createsuperuser with args
        args = argparse.Namespace(username='clisuper', password='clipassword123')
        code = cmd_createsuperuser(args)
        self.assertEqual(code, 0)

        # Test listusers
        code = cmd_listusers(argparse.Namespace())
        self.assertEqual(code, 0)

        # Test changepassword
        args_ch = argparse.Namespace(username='clisuper', password='newclipassword456')
        code = cmd_changepassword(args_ch)
        self.assertEqual(code, 0)

        # Clean up
        created = get_user_by_username('clisuper')
        if created:
            delete_user(created['id'])


if __name__ == '__main__':
    unittest.main()
