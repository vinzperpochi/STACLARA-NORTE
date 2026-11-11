"""Small helpers for consistent, server-side pagination across portal list views."""
from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from sqlalchemy import func

from app.extensions import db


def pagination_url(page, parameter='page', anchor=''):
    from flask import request, url_for
    args = request.args.to_dict(flat=False)
    for key in ('format', 'registered', '_anchor', '_external', '_scheme', '_method'):
        args.pop(key, None)
    args[parameter] = page
    args.update(request.view_args or {})
    return url_for(request.endpoint, _anchor=anchor or None, **args)


def paginate_named(query, parameter='page', per_page=5):
    from flask import request
    return paginate(query, request.args.get(parameter, 1, type=int), per_page)


def paginate_items(items, parameter='page', per_page=5):
    from flask import request
    per_page = max(1, min(int(per_page or 5), 100))
    total = len(items)
    pages = max(1, ceil(total / per_page))
    page = max(1, min(request.args.get(parameter, 1, type=int) or 1, pages))
    return Pagination(items[(page-1)*per_page:page*per_page], page, per_page, total, pages)


@dataclass(frozen=True)
class Pagination:
    items: list
    page: int
    per_page: int
    total: int
    pages: int

    @property
    def has_prev(self) -> bool:
        return self.page > 1

    @property
    def has_next(self) -> bool:
        return self.page < self.pages

    @property
    def prev_num(self) -> int | None:
        return self.page - 1 if self.has_prev else None

    @property
    def next_num(self) -> int | None:
        return self.page + 1 if self.has_next else None

    def iter_pages(self, left_edge=1, left_current=1, right_current=2, right_edge=1):
        last = 0
        for number in range(1, self.pages + 1):
            if (number <= left_edge or number > self.pages - right_edge or
                    self.page - left_current <= number <= self.page + right_current):
                if last + 1 != number:
                    yield None
                yield number
                last = number


def paginate(query, page: int | None = 1, per_page: int = 5) -> Pagination:
    """Execute a SQLAlchemy select with a bounded page and total count."""
    per_page = max(1, min(int(per_page or 5), 100))
    # Records with equal names/dates must keep their order across page requests.
    descriptions = query.column_descriptions
    if len(descriptions) == 1 and descriptions[0].get('entity') is descriptions[0].get('expr'):
        from sqlalchemy import inspect
        entity = descriptions[0].get('entity')
        if entity is not None:
            query = query.order_by(*inspect(entity).primary_key)
    total = db.session.scalar(
        db.select(func.count()).select_from(query.order_by(None).subquery())
    ) or 0
    pages = max(1, ceil(total / per_page))
    page = max(1, min(int(page or 1), pages))
    items = db.session.scalars(
        query.offset((page - 1) * per_page).limit(per_page)
    ).all()
    return Pagination(items=items, page=page, per_page=per_page, total=total, pages=pages)
