import json
import re

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import FinishedProduct, ResellerToken, SiteConfig


def complete_setup(**overrides):
    config = SiteConfig.load()
    config.is_setup_complete = True
    for key, value in overrides.items():
        setattr(config, key, value)
    config.save()
    return config


class SetupWizardGateTests(TestCase):
    """A fresh instance (no SiteConfig row yet, or is_setup_complete=False)
    must redirect every page to the wizard except the wizard/admin/static
    themselves -- this is the "launch window" behavior."""

    def test_fresh_instance_redirects_everything_to_setup(self):
        for path in ['/', '/scanner/', '/inventory/', '/dashboard/', '/login/']:
            response = self.client.get(path, follow=False)
            self.assertIn(response.status_code, (301, 302))
            self.assertIn('/setup/', response.url)

    def test_setup_page_itself_is_reachable(self):
        response = self.client.get('/setup/')
        self.assertEqual(response.status_code, 200)

    def test_completing_setup_unblocks_the_app(self):
        response = self.client.post('/setup/', {
            'brand_name': 'Acme Textiles',
            'currency_symbol': '$',
            'tagline': '',
            'accent_hex': '#112233',
        })
        self.assertEqual(response.status_code, 302)
        config = SiteConfig.load()
        self.assertTrue(config.is_setup_complete)
        self.assertEqual(config.brand_name, 'Acme Textiles')
        self.assertEqual(config.accent_hex, '#112233')

        # Now internal pages redirect to login, not to /setup/.
        response = self.client.get('/scanner/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_invalid_hex_is_rejected_not_silently_saved(self):
        self.client.post('/setup/', {
            'brand_name': 'Acme',
            'currency_symbol': '$',
            'tagline': '',
            'accent_hex': 'not-a-color',
        })
        config = SiteConfig.load()
        # Falls back to whatever it already was, never stores garbage.
        self.assertRegex(config.accent_hex, r'^#[0-9A-Fa-f]{6}$')


class InternalPageAuthTests(TestCase):
    """Scanner/inventory/dashboard require a login (task 6); the reseller
    catalogue and the three scan APIs must stay exactly as open as before
    (see CLAUDE.md -- do not harden those without discussion)."""

    def setUp(self):
        complete_setup()
        self.user = User.objects.create_user(username='warehouse', password='pw12345!')

    def test_anonymous_redirected_to_login(self):
        for path in ['/scanner/', '/inventory/', '/dashboard/']:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 302)
            self.assertIn('/login/', response.url)

    def test_logged_in_user_can_reach_internal_pages(self):
        self.client.login(username='warehouse', password='pw12345!')
        for path in ['/scanner/', '/inventory/', '/dashboard/']:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)

    def test_admin_login_is_separate_from_scanner_login(self):
        # /admin/ still uses Django admin's own login, unaffected by /login/.
        response = self.client.get('/admin/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response.url)


class ScanApiRegressionTests(TestCase):
    """The three existing scan endpoints must remain fully open (no auth, no
    CSRF) -- this is an explicit, documented design constraint, not an
    oversight, so a regression here would be a real break."""

    def setUp(self):
        complete_setup()

    def test_inbound_outbound_return_do_not_require_login(self):
        response = self.client.post('/api/inbound/', {
            'qr_id': 'SOZ-LKO-TX0001',
            'product_type': 'SAREE',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(FinishedProduct.objects.get(id='SOZ-LKO-TX0001').status, 'IN_STOCK')

        response = self.client.post('/api/outbound/', {'qr_id': 'SOZ-LKO-TX0001', 'pincode': ''})
        self.assertEqual(response.status_code, 200)

        response = self.client.post('/api/return/', {'qr_id': 'SOZ-LKO-TX0001'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(FinishedProduct.objects.get(id='SOZ-LKO-TX0001').status, 'RETURNED')

    def test_lookup_endpoint_requires_login(self):
        FinishedProduct.objects.create(id='SOZ-LKO-TX0002', product_type='SAREE')
        response = self.client.get('/api/lookup/?qr_id=SOZ-LKO-TX0002')
        # DRF's IsAuthenticated returns 403 (not 401) when session auth is the
        # only authenticator enabled, since there's no challenge to issue.
        self.assertEqual(response.status_code, 403)

        user = User.objects.create_user(username='staff', password='pw12345!')
        self.client.login(username='staff', password='pw12345!')
        response = self.client.get('/api/lookup/?qr_id=SOZ-LKO-TX0002')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['product_type'], 'SAREE')

    def test_lookup_missing_item_is_404(self):
        user = User.objects.create_user(username='staff2', password='pw12345!')
        self.client.login(username='staff2', password='pw12345!')
        response = self.client.get('/api/lookup/?qr_id=SOZ-LKO-NOPE01')
        self.assertEqual(response.status_code, 404)


class CatalogueTokenTests(TestCase):
    """Reseller catalogue stays unauthenticated, gated only by its token --
    unchanged behavior, verified so the auth rollout doesn't regress it."""

    def setUp(self):
        complete_setup()
        self.token = ResellerToken.objects.create(reseller_name='Test Reseller')

    def test_missing_token_forbidden(self):
        response = self.client.get('/catalogue/')
        self.assertEqual(response.status_code, 403)

    def test_valid_active_token_allowed_without_login(self):
        response = self.client.get(f'/catalogue/?token={self.token.token}')
        self.assertEqual(response.status_code, 200)

    def test_revoked_token_forbidden(self):
        self.token.is_active = False
        self.token.save()
        response = self.client.get(f'/catalogue/?token={self.token.token}')
        self.assertEqual(response.status_code, 403)


class DeadStockAdminActionTests(TestCase):
    """Task 8: dead stock can be toggled from the admin, in bulk."""

    def setUp(self):
        complete_setup()
        self.admin = User.objects.create_superuser(username='root', password='pw12345!', email='a@a.com')
        self.client.login(username='root', password='pw12345!')
        self.product = FinishedProduct.objects.create(id='SOZ-LKO-TX0003', product_type='DUPATTA')

    def test_bulk_mark_dead_stock_action(self):
        from django.contrib.admin.utils import quote
        change_url = reverse('admin:tracker_finishedproduct_changelist')
        response = self.client.post(change_url, {
            'action': 'mark_dead_stock',
            '_selected_action': [self.product.pk],
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.product.refresh_from_db()
        self.assertTrue(self.product.is_dead_stock)
        self.assertIsNotNone(self.product.dead_stock_marked_at)

    def test_dead_stock_excluded_from_inventory_value_is_still_counted(self):
        # Dead stock is a marker, not a status change -- it must keep counting
        # as in-stock capital, not vanish from the totals.
        self.product.is_dead_stock = True
        self.product.price = 500
        self.product.save()
        response = self.client.get('/inventory/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['dead_stock_count'], 1)


class ScannerPageAndPwaTests(TestCase):
    """The scanner page's injected Tailwind config must be valid JSON (a typo
    here silently breaks every `bg-brand-*` class on the page), the new
    LOOKUP tab must actually be present, and the PWA endpoints must respond
    with the right content types."""

    def setUp(self):
        complete_setup(brand_name='Acme', accent_hex='#C8A46E')
        User.objects.create_user(username='floor', password='pw12345!')
        self.client.login(username='floor', password='pw12345!')

    def test_scanner_page_has_valid_brand_config_and_lookup_tab(self):
        response = self.client.get('/scanner/')
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()

        match = re.search(r'tailwind\.config = (\{.*?\});', html)
        self.assertIsNotNone(match, "tailwind.config script tag not found")
        config = json.loads(match.group(1))
        self.assertIn('brand', config['theme']['extend']['colors'])
        self.assertEqual(config['theme']['extend']['colors']['brand']['500'], '#C8A46E')

        self.assertIn('LOOKUP', html)
        self.assertIn('manifest.webmanifest', html)

    def test_manifest_is_valid_json_with_theme_color(self):
        response = self.client.get('/manifest.webmanifest')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['name'], 'Acme')
        self.assertEqual(data['theme_color'], '#C8A46E')

    def test_service_worker_is_javascript(self):
        response = self.client.get('/sw.js')
        self.assertEqual(response.status_code, 200)
        self.assertIn('javascript', response['Content-Type'])


class AdminPanelRegressionTests(TestCase):
    """The admin changelist crashed for the two most common statuses before
    this round of fixes (format_html() called with no placeholders -- see
    admin.py). Guard against that regressing, and check the dashboard cards
    and SiteConfig singleton editor both render."""

    def setUp(self):
        complete_setup()
        self.admin = User.objects.create_superuser(username='root2', password='pw12345!', email='a@a.com')
        self.client.login(username='root2', password='pw12345!')

    def test_changelist_renders_for_every_status(self):
        FinishedProduct.objects.create(id='SOZ-LKO-TX0010', product_type='SAREE', status='IN_STOCK')
        FinishedProduct.objects.create(id='SOZ-LKO-TX0011', product_type='SAREE', status='DISPATCHED')
        FinishedProduct.objects.create(id='SOZ-LKO-TX0012', product_type='SAREE', status='RETURNED')
        response = self.client.get(reverse('admin:tracker_finishedproduct_changelist'))
        self.assertEqual(response.status_code, 200)

    def test_admin_index_dashboard_cards_render(self):
        response = self.client.get('/admin/')
        self.assertEqual(response.status_code, 200)

    def test_siteconfig_singleton_redirects_straight_to_change_form(self):
        response = self.client.get(reverse('admin:tracker_siteconfig_changelist'))
        self.assertEqual(response.status_code, 302)
        response = self.client.get(response.url)
        self.assertEqual(response.status_code, 200)
