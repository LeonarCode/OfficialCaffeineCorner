"""
Customer ratings as the admin shows them on a product: the average, how many of
each star, and the latest reviews (see ProductAdmin.rating_summary and
templates/admin/online_shop/product/_rating_summary.html).

Ratings live on the product now — there is no separate Ratings entry in the
sidebar; a product's page is where you read what customers think of it.
"""
from django.db.models import Count
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe

STAR_ROWS = (5, 4, 3, 2, 1)


def tone(average):
    """good / mid / low — decides the colour a rating is shown in."""
    if average is None:
        return 'none'
    return 'good' if average >= 4 else 'mid' if average >= 3 else 'low'


def stars_markup(filled, small=False):
    """★★★★☆ — `filled` stars lit, the rest dimmed."""
    stars = format_html_join(
        '', '<span{}>★</span>',
        ((mark_safe('') if number <= filled else mark_safe(' class="off"'),) for number in range(1, 6)),
    )
    return format_html(
        '<span class="an-stars{}" role="img" aria-label="{} out of 5 stars">{}</span>',
        ' an-stars--sm' if small else '', filled, stars,
    )


def summarize(product, latest=6):
    counts = dict(product.ratings.order_by().values_list('rating').annotate(n=Count('id')))
    total = sum(counts.values())
    average = sum(stars * n for stars, n in counts.items()) / total if total else None
    reviews = [
        {
            'who': rating.user.get_full_name() or rating.user.email,
            'stars': stars_markup(rating.rating, small=True),
            'text': rating.review,
            'when': rating.created_at,
        }
        for rating in product.ratings.select_related('user').order_by('-created_at')[:latest]
    ]
    return {
        'count': total,
        'average': round(average, 1) if average is not None else None,
        'tone': tone(average),
        'stars': stars_markup(round(average)) if average is not None else '',
        'distribution': [
            {'stars': stars, 'count': counts.get(stars, 0), 'pct': round(counts.get(stars, 0) / total * 100) if total else 0}
            for stars in STAR_ROWS
        ],
        'reviews': reviews,
    }
