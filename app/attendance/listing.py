"""Bound attendance lists, including records calculated from dates and personnel."""
from math import ceil

from flask import request, url_for

from app.pagination import Pagination


def page_size():
    size = request.args.get('per_page', 5, type=int)
    return size if size in (5, 10, 25, 50) else 5


def page_window(total, parameter='page', size=None):
    size = size or page_size()
    pages = max(1, ceil(total / size))
    page = max(1, min(request.args.get(parameter, 1, type=int), pages))
    return Pagination(items=[], page=page, per_page=size, total=total, pages=pages)


def page_items(items, parameter='page', size=None):
    window = page_window(len(items), parameter, size)
    offset = (window.page - 1) * window.per_page
    return Pagination(items=items[offset:offset + window.per_page], page=window.page,
                      per_page=window.per_page, total=window.total, pages=window.pages)


def list_url(page, parameter, anchor):
    args = request.args.to_dict()
    for key in ('format', 'registered', '_anchor'):
        args.pop(key, None)
    args.update(request.view_args or {})
    args[parameter] = page
    return url_for(request.endpoint, _anchor=anchor, **args)


def dashboard_return_url(anchor, **overrides):
    keys = ('date', 'q', 'department', 'personnel_id', 'status', 'period',
            'per_page', 'page', 'feed_page', 'leave_page')
    args = {key: request.args[key] for key in keys if key in request.args}
    args.update(overrides)
    return url_for('attendance.dashboard', _anchor=anchor, **args)
