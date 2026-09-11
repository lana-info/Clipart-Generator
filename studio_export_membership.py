"""Validated project-level set assignments; no credentials or export paths."""


def validate_export_membership(value):
    if not isinstance(value, dict) or len(value) > 10000:
        raise ValueError('Допускается до 10000 сохранённых назначений PNG')
    result = {}
    for path, item in value.items():
        if not isinstance(path, str) or not 1 <= len(path) <= 4000:
            raise ValueError('Неверный путь PNG в распределении наборов')
        if (not isinstance(item, dict) or set(item) != {'title', 'included'}
                or not isinstance(item['title'], str) or not item['title'].strip()
                or len(item['title']) > 200 or type(item['included']) is not bool):
            raise ValueError('Неверное назначение PNG набору')
        result[path] = dict(item)
    return result
