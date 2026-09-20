"""
Every automated test for the project lives in this folder.

Nothing in the apps imports from here, so the whole `tests/` folder can be left
out of a production deploy.

    tests/support/            shared helpers: factories, admin form posting, the browser base class
    tests/test_inventory/     inventory, purchase orders, stock movements, the Sales Report
    tests/test_online_shop/   orders and price snapshots, the admin's JavaScript helpers
    tests/test_authentication/

Run them from the folder that has manage.py:

    python manage.py test                                      everything
    python manage.py test tests.test_inventory                 one area
    python manage.py test tests.test_inventory.test_stock_rules   one file

The *_browser tests drive a real Chromium through Playwright, a dev-only tool that
is not in the Pipfile; they skip themselves when it isn't installed.
"""
