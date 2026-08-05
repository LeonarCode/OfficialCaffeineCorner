def unfold_admin_theme(request):
    """Injects Unfold's `element_classes` hook so the admin sidebar/header
    templates pick up extra classes without having to override them."""
    return {
        'element_classes': {
            'navigation': 'cc-sidebar',
            'navigation_inner': 'cc-sidebar',
            'navigation_header': 'cc-sidebar-header',
            'header': 'cc-header',
        },
    }
