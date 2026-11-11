"""Safe sorting shared by registry controllers."""
from flask import request
from sqlalchemy import inspect

def apply_sort(query, model, default_column='created_at', default_order='desc'):
    columns = inspect(model).column_attrs.keys()
    name = request.args.get('sort', default_column)
    if name not in columns:
        name = default_column if default_column in columns else 'id'
    order = request.args.get('order', default_order).lower()
    if order not in ('asc', 'desc'):
        order = default_order
    column = getattr(model, name)
    return query.order_by(column.desc() if order == 'desc' else column.asc())
