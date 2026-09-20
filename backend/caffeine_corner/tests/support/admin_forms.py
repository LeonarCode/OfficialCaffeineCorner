"""Helpers for driving the Django admin's forms from a test."""


def admin_post_data(response, **overrides):
    """
    The POST a browser would send back for the admin change form in `response`
    (main form + inline formsets, as currently displayed), with `overrides`
    applied on top — so a test edits one field the way staff would, not by
    hand-building every management-form key.
    """
    data = {}

    def take(form):
        prefix = f'{form.prefix}-' if form.prefix else ''
        for name in form.fields:
            value = form[name].value()
            if value is None or value is False or value == '':
                continue
            data[f'{prefix}{name}'] = 'on' if value is True else value

    ctx = response.context
    take(ctx['adminform'].form)
    for inline in ctx['inline_admin_formsets']:
        formset = inline.formset
        for key, value in formset.management_form.initial.items():
            data[f'{formset.prefix}-{key}'] = value
        for form in formset.forms:
            take(form)
    data.update(overrides)
    return data
